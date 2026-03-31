package com.example.emotune

import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.spotify.android.appremote.api.ConnectionParams
import com.spotify.android.appremote.api.Connector
import com.spotify.android.appremote.api.SpotifyAppRemote
import com.spotify.protocol.client.Subscription
import com.spotify.protocol.types.ImageUri
import com.spotify.protocol.types.ListItem
import com.spotify.protocol.types.PlayerContext
import com.spotify.protocol.types.PlayerState
import com.spotify.sdk.android.auth.AuthorizationClient
import com.spotify.sdk.android.auth.AuthorizationRequest
import com.spotify.sdk.android.auth.AuthorizationResponse
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity(), EventChannel.StreamHandler {
    companion object {
        private const val TAG = "EmoTuneSpotify"
        private const val METHOD_CHANNEL = "emotune/spotify_remote"
        private const val EVENT_CHANNEL = "emotune/spotify_remote_events"
        private const val SPOTIFY_PACKAGE_NAME = "com.spotify.music"
        private const val APP_REMOTE_AUTH_REQUEST_CODE = 0x5150
        private const val SPOTIFY_FOREGROUND_DELAY_MS = 1500L
        private val APP_REMOTE_AUTH_SCOPES = arrayOf("app-remote-control")
    }

    private data class PendingAppRemoteAuthorization(
        val onAuthorized: () -> Unit,
        val onError: (Throwable) -> Unit,
    )

    private class PlaybackAuthorizationFailedException(
        message: String,
    ) : RuntimeException(message)

    private class PlaybackAuthorizationCancelledException :
        RuntimeException("Spotify playback approval was cancelled on this device.")

    private var spotifyAppRemote: SpotifyAppRemote? = null
    private var playerStateSubscription: Subscription<PlayerState>? = null
    private var playerContextSubscription: Subscription<PlayerContext>? = null
    private var eventSink: EventChannel.EventSink? = null
    private var lastPlayerState: PlayerState? = null
    private var lastPlayerContext: PlayerContext? = null
    private var authViewPending = false
    private var lastAuthViewRequested = false
    private var lastAuthViewSurfaced = false
    private var pendingAppRemoteAuthorization: PendingAppRemoteAuthorization? = null
    private var appRemoteAuthorizedThisSession = false
    private val mainHandler = Handler(Looper.getMainLooper())

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, METHOD_CHANNEL)
            .setMethodCallHandler(::handleMethodCall)

        EventChannel(flutterEngine.dartExecutor.binaryMessenger, EVENT_CHANNEL)
            .setStreamHandler(this)
    }

    override fun onListen(arguments: Any?, events: EventChannel.EventSink) {
        eventSink = events
    }

    override fun onCancel(arguments: Any?) {
        eventSink = null
    }

    override fun onPause() {
        if (authViewPending && !lastAuthViewSurfaced) {
            lastAuthViewSurfaced = true
            sendDebugEvent(
                "auth_view_surface_detected",
                "Spotify approval UI moved EmoTune to the background.",
            )
        }
        super.onPause()
    }

    override fun onStop() {
        super.onStop()
        if (pendingAppRemoteAuthorization != null || authViewPending) {
            sendDebugEvent(
                "disconnect_skipped",
                "Keeping Spotify state intact while authorization is in progress.",
            )
            return
        }
        disconnectRemote()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)

        if (requestCode != APP_REMOTE_AUTH_REQUEST_CODE) {
            return
        }

        val pendingAuthorization = pendingAppRemoteAuthorization ?: return
        pendingAppRemoteAuthorization = null

        val response = AuthorizationClient.getResponse(resultCode, data)
        val payload = hashMapOf<String, Any?>(
            "response_type" to response.type.name,
            "error" to response.error,
        )

        when (response.type) {
            AuthorizationResponse.Type.TOKEN,
            AuthorizationResponse.Type.CODE -> {
                appRemoteAuthorizedThisSession = true
                lastAuthViewRequested = true
                lastAuthViewSurfaced = true
                finishAuthViewTracking()
                sendDebugEvent(
                    "auth_callback_received",
                    "Spotify playback authorization completed on-device.",
                    payload.apply {
                        put("expires_in", response.expiresIn)
                        put("used_explicit_auth", true)
                    },
                )
                pendingAuthorization.onAuthorized()
            }
            AuthorizationResponse.Type.ERROR -> {
                finishAuthViewTracking()
                sendDebugEvent(
                    "auth_callback_failed",
                    "Spotify playback authorization failed on-device.",
                    payload,
                )
                pendingAuthorization.onError(
                    PlaybackAuthorizationFailedException(
                        response.error?.takeIf { it.isNotBlank() }
                            ?: "Spotify playback approval failed on this device.",
                    ),
                )
            }
            else -> {
                finishAuthViewTracking()
                sendDebugEvent(
                    "auth_callback_cancelled",
                    "Spotify playback authorization was cancelled on-device.",
                    payload,
                )
                pendingAuthorization.onError(PlaybackAuthorizationCancelledException())
            }
        }
    }

    private fun handleMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "isSpotifyAppInstalled" -> result.success(isSpotifyAppInstalled())
            "openSpotifyApp" -> result.success(launchSpotifyAppIfInstalled())
            "connect" -> connect(call, result)
            "disconnect" -> {
                disconnectRemote()
                result.success(true)
            }
            "isConnected" -> result.success(spotifyAppRemote != null)
            "playUri" -> playUri(call, result)
            "pause" -> withRemote(result) { remote ->
                remote.playerApi.pause()
                    .setResultCallback {
                        requestCurrentPlayerState()
                        result.success(true)
                    }
                    .setErrorCallback { error ->
                        val message = reportError("pause_failed", error)
                        result.error("pause_failed", message, errorDetails(error))
                    }
            }
            "resume" -> withRemote(result) { remote ->
                remote.playerApi.resume()
                    .setResultCallback {
                        requestCurrentPlayerState()
                        result.success(true)
                    }
                    .setErrorCallback { error ->
                        val message = reportError("resume_failed", error)
                        result.error("resume_failed", message, errorDetails(error))
                    }
            }
            "togglePlayPause" -> togglePlayPause(result)
            "skipNext" -> withRemote(result) { remote ->
                remote.playerApi.skipNext()
                    .setResultCallback {
                        requestCurrentPlayerState()
                        result.success(true)
                    }
                    .setErrorCallback { error ->
                        val message = reportError("skip_next_failed", error)
                        result.error("skip_next_failed", message, errorDetails(error))
                    }
            }
            "skipPrevious" -> withRemote(result) { remote ->
                remote.playerApi.skipPrevious()
                    .setResultCallback {
                        requestCurrentPlayerState()
                        result.success(true)
                    }
                    .setErrorCallback { error ->
                        val message = reportError("skip_previous_failed", error)
                        result.error("skip_previous_failed", message, errorDetails(error))
                    }
            }
            "seekTo" -> withRemote(result) { remote ->
                val positionMs = (call.argument<Number>("positionMs") ?: 0).toLong()
                remote.playerApi.seekTo(positionMs)
                    .setResultCallback {
                        requestCurrentPlayerState()
                        result.success(true)
                    }
                    .setErrorCallback { error ->
                        val message = reportError("seek_failed", error)
                        result.error("seek_failed", message, errorDetails(error))
                    }
            }
            "refreshPlayerState" -> withRemote(result) {
                requestCurrentPlayerState()
                result.success(true)
            }
            else -> result.notImplemented()
        }
    }

    private fun connect(call: MethodCall, result: MethodChannel.Result) {
        val clientId = call.argument<String>("clientId").orEmpty()
        val redirectUri = call.argument<String>("redirectUri").orEmpty()
        val showAuthView = call.argument<Boolean>("showAuthView") ?: true
        val allowForegroundLaunch = call.argument<Boolean>("allowForegroundLaunch") ?: true

        if (clientId.isBlank() || redirectUri.isBlank()) {
            result.error(
                "invalid_config",
                "Spotify client ID or redirect URI is missing.",
                null,
            )
            return
        }

        ensureConnected(
            clientId = clientId,
            redirectUri = redirectUri,
            showAuthView = showAuthView,
            allowForegroundLaunch = allowForegroundLaunch,
            forceReconnect = showAuthView,
            onConnected = { result.success(true) },
            onError = { error ->
                val message = reportError("connect_failed", error)
                result.error("connect_failed", message, errorDetails(error))
            },
        )
    }

    private fun playUri(call: MethodCall, result: MethodChannel.Result) {
        val uri = call.argument<String>("uri").orEmpty()
        val clientId = call.argument<String>("clientId").orEmpty()
        val redirectUri = call.argument<String>("redirectUri").orEmpty()
        val showAuthView = call.argument<Boolean>("showAuthView") ?: true
        val allowForegroundLaunch = call.argument<Boolean>("allowForegroundLaunch") ?: true

        if (uri.isBlank()) {
            result.error("invalid_uri", "Track URI is missing.", null)
            return
        }

        playWithRemote(
            uri = uri,
            clientId = clientId,
            redirectUri = redirectUri,
            showAuthView = showAuthView,
            allowForegroundLaunch = allowForegroundLaunch,
            allowReconnect = showAuthView,
            result = result,
        )
    }

    private fun playWithRemote(
        uri: String,
        clientId: String,
        redirectUri: String,
        showAuthView: Boolean,
        allowForegroundLaunch: Boolean,
        allowReconnect: Boolean,
        result: MethodChannel.Result,
    ) {
        sendDebugEvent(
            "play_attempt",
            "Requesting Spotify playback for $uri",
            hashMapOf(
                "show_auth_view" to showAuthView,
                "allow_foreground_launch" to allowForegroundLaunch,
                "allow_reconnect" to allowReconnect,
            ),
        )
        ensureConnected(
            clientId = clientId,
            redirectUri = redirectUri,
            showAuthView = showAuthView,
            allowForegroundLaunch = allowForegroundLaunch,
            forceReconnect = false,
            onConnected = { remote ->
                remote.playerApi.play(uri)
                    .setResultCallback {
                        requestCurrentPlayerState()
                        result.success(true)
                    }
                    .setErrorCallback { error ->
                        if (allowReconnect && shouldRetryWithFreshAuthorization(error)) {
                            retryPlaybackAuthorization(
                                uri = uri,
                                clientId = clientId,
                                redirectUri = redirectUri,
                                result = result,
                            )
                            return@setErrorCallback
                        }

                        val message = reportError("play_failed", error)
                        result.error("play_failed", message, errorDetails(error))
                    }
            },
            onError = { error ->
                val message = reportError("connect_failed", error)
                result.error("connect_failed", message, errorDetails(error))
            },
        )
    }

    private fun retryPlaybackAuthorization(
        uri: String,
        clientId: String,
        redirectUri: String,
        result: MethodChannel.Result,
    ) {
        sendDebugEvent(
            "play_retry_authorization",
            "Retrying Spotify playback after a fresh authorization prompt.",
        )
        disconnectRemote()
        playWithRemote(
            uri = uri,
            clientId = clientId,
            redirectUri = redirectUri,
            showAuthView = true,
            allowForegroundLaunch = true,
            allowReconnect = false,
            result = result,
        )
    }

    private fun togglePlayPause(result: MethodChannel.Result) {
        withRemote(result) { remote ->
            val playerState = lastPlayerState
            if (playerState != null) {
                if (playerState.isPaused) {
                    remote.playerApi.resume()
                        .setResultCallback { result.success(true) }
                        .setErrorCallback { error ->
                            val message = reportError("resume_failed", error)
                            result.error("resume_failed", message, errorDetails(error))
                        }
                } else {
                    remote.playerApi.pause()
                        .setResultCallback { result.success(true) }
                        .setErrorCallback { error ->
                            val message = reportError("pause_failed", error)
                            result.error("pause_failed", message, errorDetails(error))
                        }
                }
            } else {
                remote.playerApi.playerState
                    .setResultCallback { currentState ->
                        lastPlayerState = currentState
                        togglePlayPause(result)
                    }
                    .setErrorCallback { error ->
                        val message = reportError("player_state_failed", error)
                        result.error("player_state_failed", message, errorDetails(error))
                    }
            }
        }
    }

    private fun ensureConnected(
        clientId: String,
        redirectUri: String,
        showAuthView: Boolean,
        allowForegroundLaunch: Boolean,
        forceReconnect: Boolean,
        onConnected: (SpotifyAppRemote) -> Unit,
        onError: (Throwable) -> Unit,
    ) {
        ensurePlaybackAuthorization(
            clientId = clientId,
            redirectUri = redirectUri,
            showAuthView = showAuthView,
            onAuthorized = {
                connectToSpotifyAppRemote(
                    clientId = clientId,
                    redirectUri = redirectUri,
                    showAuthView = false,
                    allowForegroundLaunch = allowForegroundLaunch,
                    forceReconnect = forceReconnect,
                    onConnected = onConnected,
                    onError = onError,
                )
            },
            onError = onError,
        )
    }

    private fun ensurePlaybackAuthorization(
        clientId: String,
        redirectUri: String,
        showAuthView: Boolean,
        onAuthorized: () -> Unit,
        onError: (Throwable) -> Unit,
    ) {
        if (!showAuthView || appRemoteAuthorizedThisSession) {
            onAuthorized()
            return
        }

        if (pendingAppRemoteAuthorization != null) {
            onError(
                PlaybackAuthorizationFailedException(
                    "Spotify playback approval is already in progress on this device.",
                ),
            )
            return
        }

        beginAuthViewTracking(true)

        val request = AuthorizationRequest.Builder(
            clientId,
            AuthorizationResponse.Type.TOKEN,
            redirectUri,
        )
            .setScopes(APP_REMOTE_AUTH_SCOPES)
            .setShowDialog(true)
            .build()

        pendingAppRemoteAuthorization = PendingAppRemoteAuthorization(
            onAuthorized = onAuthorized,
            onError = onError,
        )

        sendDebugEvent(
            "auth_request_start",
            "Starting explicit Spotify playback authorization.",
            hashMapOf(
                "redirect_uri" to redirectUri,
                "scopes" to APP_REMOTE_AUTH_SCOPES.joinToString(" "),
                "used_explicit_auth" to true,
            ),
        )

        try {
            AuthorizationClient.openLoginActivity(
                this,
                APP_REMOTE_AUTH_REQUEST_CODE,
                request,
            )
        } catch (error: Throwable) {
            pendingAppRemoteAuthorization = null
            finishAuthViewTracking()
            onError(
                PlaybackAuthorizationFailedException(
                    error.message?.takeIf { it.isNotBlank() }
                        ?: "Spotify playback approval could not be started on this device.",
                ),
            )
        }
    }

    private fun connectToSpotifyAppRemote(
        clientId: String,
        redirectUri: String,
        showAuthView: Boolean,
        allowForegroundLaunch: Boolean,
        forceReconnect: Boolean,
        hasRetriedAfterForegroundLaunch: Boolean = false,
        onConnected: (SpotifyAppRemote) -> Unit,
        onError: (Throwable) -> Unit,
    ) {
        if (forceReconnect) {
            disconnectRemote()
        }

        spotifyAppRemote?.let {
            onConnected(it)
            return
        }

        val connectionParams = ConnectionParams.Builder(clientId)
            .setRedirectUri(redirectUri)
            .showAuthView(showAuthView)
            .build()

        val connectAction = Runnable {
            sendDebugEvent(
                "connect_attempt",
                "Connecting to Spotify App Remote.",
                hashMapOf(
                    "show_auth_view" to showAuthView,
                    "force_reconnect" to forceReconnect,
                    "allow_foreground_launch" to allowForegroundLaunch,
                    "foreground_retry" to hasRetriedAfterForegroundLaunch,
                    "redirect_uri" to redirectUri,
                ),
            )
            SpotifyAppRemote.connect(
                application,
                connectionParams,
                object : Connector.ConnectionListener {
                    override fun onConnected(appRemote: SpotifyAppRemote) {
                        finishAuthViewTracking()
                        appRemoteAuthorizedThisSession = true
                        spotifyAppRemote = appRemote
                        sendEvent(
                            hashMapOf(
                                "type" to "connected",
                            ),
                        )
                        subscribeToPlayerState()
                        subscribeToPlayerContext()
                        requestCurrentPlayerState()
                        fetchCapabilities()
                        sendDebugEvent(
                            "connect_success",
                            "Spotify App Remote connected successfully.",
                        )
                        onConnected(appRemote)
                    }

                    override fun onFailure(error: Throwable) {
                        if (
                            allowForegroundLaunch &&
                            !hasRetriedAfterForegroundLaunch &&
                            shouldRetryAfterForegroundLaunch(error) &&
                            launchSpotifyAppIfInstalled()
                        ) {
                            sendDebugEvent(
                                "connect_retry_after_foreground_launch",
                                "Retrying Spotify App Remote after waking the Spotify app once.",
                                hashMapOf(
                                    "native_error_type" to error.javaClass.simpleName,
                                ),
                            )
                            mainHandler.postDelayed(
                                {
                                    connectToSpotifyAppRemote(
                                        clientId = clientId,
                                        redirectUri = redirectUri,
                                        showAuthView = showAuthView,
                                        allowForegroundLaunch = false,
                                        forceReconnect = true,
                                        hasRetriedAfterForegroundLaunch = true,
                                        onConnected = onConnected,
                                        onError = onError,
                                    )
                                },
                                SPOTIFY_FOREGROUND_DELAY_MS,
                            )
                            return
                        }
                        finishAuthViewTracking()
                        if (lastAuthViewRequested && !lastAuthViewSurfaced) {
                            sendDebugEvent(
                                "auth_view_not_surfaced",
                                "Spotify approval UI was requested but did not appear above EmoTune.",
                                hashMapOf(
                                    "native_error_type" to error.javaClass.simpleName,
                                    "manufacturer" to Build.MANUFACTURER,
                                    "model" to Build.MODEL,
                                ),
                            )
                        }
                        sendDebugEvent(
                            "connect_failure",
                            "Spotify App Remote connection failed.",
                            hashMapOf(
                                "native_error_type" to error.javaClass.simpleName,
                                "raw_message" to error.message,
                            ),
                        )
                        onError(error)
                    }
                },
            )
        }

        connectAction.run()
    }

    private fun launchSpotifyAppIfInstalled(): Boolean {
        val launchIntent = packageManager.getLaunchIntentForPackage(SPOTIFY_PACKAGE_NAME) ?: return false
        launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            startActivity(launchIntent)
            sendDebugEvent(
                "spotify_app_launch",
                "Brought the Spotify app to the foreground before App Remote connection.",
            )
            return true
        } catch (error: Throwable) {
            sendDebugEvent(
                "spotify_app_launch_failed",
                "Could not foreground the Spotify app before App Remote connection.",
                hashMapOf("raw_message" to error.message),
            )
            return false
        }
    }

    private fun isSpotifyAppInstalled(): Boolean {
        return packageManager.getLaunchIntentForPackage(SPOTIFY_PACKAGE_NAME) != null
    }

    private fun withRemote(
        result: MethodChannel.Result,
        action: (SpotifyAppRemote) -> Unit,
    ) {
        val remote = spotifyAppRemote
        if (remote == null) {
            result.error(
                "not_connected",
                "Spotify is not connected on this device.",
                null,
            )
            return
        }
        action(remote)
    }

    private fun subscribeToPlayerState() {
        cancelSubscription(playerStateSubscription)

        val remote = spotifyAppRemote ?: return
        @Suppress("UNCHECKED_CAST")
        playerStateSubscription = remote.playerApi.subscribeToPlayerState()
            .setEventCallback { playerState ->
                lastPlayerState = playerState
                sendPlayerState(playerState)
            }
            .setErrorCallback { error ->
                reportError("player_state_subscription_failed", error)
            } as Subscription<PlayerState>
    }

    private fun subscribeToPlayerContext() {
        cancelSubscription(playerContextSubscription)

        val remote = spotifyAppRemote ?: return
        @Suppress("UNCHECKED_CAST")
        playerContextSubscription = remote.playerApi.subscribeToPlayerContext()
            .setEventCallback { playerContext ->
                lastPlayerContext = playerContext
                sendPlayerContext(playerContext)
                requestContextQueue(playerContext)
            }
            .setErrorCallback { error ->
                reportError("player_context_subscription_failed", error)
            } as Subscription<PlayerContext>
    }

    private fun requestCurrentPlayerState() {
        spotifyAppRemote?.playerApi?.playerState
            ?.setResultCallback { playerState ->
                lastPlayerState = playerState
                sendPlayerState(playerState)
            }
            ?.setErrorCallback { error ->
                reportError("player_state_failed", error)
            }
    }

    private fun fetchCapabilities() {
        spotifyAppRemote?.userApi?.capabilities
            ?.setResultCallback { capabilities ->
                sendEvent(
                    hashMapOf(
                        "type" to "capabilities",
                        "can_play_on_demand" to capabilities.canPlayOnDemand,
                    ),
                )
            }
            ?.setErrorCallback { error ->
                reportError("capabilities_failed", error)
            }
    }

    private fun disconnectRemote() {
        cancelSubscription(playerStateSubscription)
        playerStateSubscription = null
        cancelSubscription(playerContextSubscription)
        playerContextSubscription = null
        lastPlayerState = null
        lastPlayerContext = null

        spotifyAppRemote?.let { remote ->
            SpotifyAppRemote.disconnect(remote)
            spotifyAppRemote = null
            sendEvent(hashMapOf("type" to "disconnected"))
        }
    }

    private fun sendPlayerState(playerState: PlayerState) {
        val track = playerState.track
        sendEvent(
            hashMapOf(
                "type" to "player_state",
                "is_paused" to playerState.isPaused,
                "position_ms" to playerState.playbackPosition,
                "track" to hashMapOf(
                    "uri" to track?.uri,
                    "name" to track?.name,
                    "artist" to track?.artist?.name,
                    "duration_ms" to track?.duration,
                    "image_uri" to track?.imageUri?.toString(),
                ),
            ),
        )
    }

    private fun sendPlayerContext(playerContext: PlayerContext) {
        val contextUri = playerContext.uri.orEmpty()
        val contextType = playerContext.type?.takeIf { it.isNotBlank() }
            ?: inferSpotifyType(contextUri)

        sendEvent(
            hashMapOf(
                "type" to "player_context",
                "context" to hashMapOf(
                    "uri" to contextUri,
                    "title" to playerContext.title,
                    "subtitle" to playerContext.subtitle,
                    "type" to contextType,
                ),
            ),
        )
    }

    private fun requestContextQueue(playerContext: PlayerContext) {
        val contextUri = playerContext.uri.orEmpty()
        val contextType = playerContext.type?.takeIf { it.isNotBlank() }
            ?: inferSpotifyType(contextUri)

        if (contextUri.isBlank() || !supportsQueueLookup(contextType)) {
            sendEvent(
                hashMapOf(
                    "type" to "context_queue",
                    "context_uri" to contextUri,
                    "items" to arrayListOf<HashMap<String, Any?>>(),
                ),
            )
            return
        }

        val remote = spotifyAppRemote ?: return
        val parent = ListItem(
            extractSpotifyId(contextUri),
            contextUri,
            ImageUri(""),
            playerContext.title.orEmpty(),
            playerContext.subtitle.orEmpty(),
            false,
            true,
        )

        remote.contentApi.getChildrenOfItem(parent, 50, 0)
            .setResultCallback { listItems ->
                val items = ArrayList<HashMap<String, Any?>>(listItems.items.size)
                listItems.items.forEach { item ->
                    items.add(
                        hashMapOf(
                            "id" to item.id,
                            "uri" to item.uri,
                            "name" to item.title,
                            "artist" to item.subtitle,
                            "album" to playerContext.title,
                            "item_type" to inferSpotifyType(item.uri),
                            "spotify_url" to toSpotifyUrl(item.uri),
                            "image_uri" to item.imageUri?.raw,
                            "preview_url" to null,
                            "duration_ms" to 0,
                            "is_playable" to item.playable,
                            "has_children" to item.hasChildren,
                        ),
                    )
                }
                sendEvent(
                    hashMapOf(
                        "type" to "context_queue",
                        "context_uri" to contextUri,
                        "items" to items,
                    ),
                )
            }
            .setErrorCallback { error ->
                reportError("context_queue_failed", error)
                sendEvent(
                    hashMapOf(
                        "type" to "context_queue",
                        "context_uri" to contextUri,
                        "items" to arrayListOf<HashMap<String, Any?>>(),
                    ),
                )
            }
    }

    private fun reportError(code: String, error: Throwable): String {
        val message = toUserMessage(error)
        Log.e(TAG, "Spotify remote error [$code]: $message", error)
        sendEvent(
            hashMapOf(
                "type" to "error",
                "code" to code,
                "message" to message,
                "native_error_type" to error.javaClass.simpleName,
                "raw_message" to error.message,
            ),
        )
        return message
    }

    private fun sendDebugEvent(
        step: String,
        message: String,
        payload: HashMap<String, Any?> = hashMapOf(),
    ) {
        val payloadSummary = payload.entries.joinToString(", ") { (key, value) ->
            "$key=$value"
        }
        Log.d(
            TAG,
            buildString {
                append("Spotify debug [")
                append(step)
                append("]: ")
                append(message)
                if (payloadSummary.isNotBlank()) {
                    append(" (")
                    append(payloadSummary)
                    append(")")
                }
            },
        )
        sendEvent(
            hashMapOf<String, Any?>(
                "type" to "debug",
                "step" to step,
                "message" to message,
            ).apply { putAll(payload) },
        )
    }

    private fun errorDetails(error: Throwable): HashMap<String, Any?> {
        return hashMapOf(
            "nativeErrorType" to error.javaClass.simpleName,
            "rawMessage" to error.message,
            "authViewRequested" to lastAuthViewRequested,
            "authViewSurfaceDetected" to lastAuthViewSurfaced,
            "deviceManufacturer" to Build.MANUFACTURER,
            "deviceModel" to Build.MODEL,
        )
    }

    private fun shouldRetryWithFreshAuthorization(error: Throwable): Boolean {
        return error.javaClass.simpleName == "UserNotAuthorizedException"
    }

    private fun shouldRetryAfterForegroundLaunch(error: Throwable): Boolean {
        return when (error.javaClass.simpleName) {
            "CouldNotFindSpotifyApp",
            "UserNotAuthorizedException",
            "PlaybackAuthorizationFailedException",
            "PlaybackAuthorizationCancelledException",
            "AuthenticationFailedException" -> false
            else -> true
        }
    }

    private fun toUserMessage(error: Throwable): String {
        val defaultMessage = error.message?.takeIf { it.isNotBlank() } ?: "Spotify playback failed."
        return when (error.javaClass.simpleName) {
            "CouldNotFindSpotifyApp" ->
                "Install and log in to the Spotify app on this device to enable in-app playback."
            "PlaybackAuthorizationFailedException" ->
                "Spotify playback approval could not be completed on this device. EmoTune will open Spotify to request app-remote-control access, then you can try the song again."
            "PlaybackAuthorizationCancelledException" ->
                "Spotify playback approval was cancelled. Approve Spotify access for EmoTune, then try the song again."
            "UserNotAuthorizedException" ->
                approvalMessageForUserAuthorizationError()
            "AuthenticationFailedException" ->
                "Spotify playback authorization failed. Reconnect Spotify and confirm the Spotify dashboard includes emotune://spotify-auth-callback."
            "NotLoggedInException" ->
                "Log in to the Spotify app on this device, then try again."
            "OfflineModeException" ->
                "Spotify is offline on this device. Reconnect to the internet and try again."
            "UnsupportedFeatureVersionException" ->
                "Update the Spotify app on this device to enable in-app playback."
            else -> defaultMessage
        }
    }

    private fun beginAuthViewTracking(showAuthView: Boolean) {
        authViewPending = showAuthView
        lastAuthViewRequested = showAuthView
        lastAuthViewSurfaced = false
    }

    private fun finishAuthViewTracking() {
        authViewPending = false
    }

    private fun approvalMessageForUserAuthorizationError(): String {
        if (lastAuthViewRequested && !lastAuthViewSurfaced) {
            return if (isXiaomiFamilyDevice()) {
                "Spotify connected, but playback permission or active device is missing. The Spotify approval sheet did not appear on this Xiaomi device. Keep the phone unlocked, allow Spotify pop-ups/background starts if needed, then tap Approve Playback in EmoTune again."
            } else {
                "Spotify connected, but playback permission or active device is missing. The Spotify approval sheet did not appear on this phone. Keep the phone unlocked, then tap Approve Playback in EmoTune again."
            }
        }

        return "Spotify connected, but playback permission or active device is still missing. Approve the Spotify prompt on this phone, then try the song again."
    }

    private fun isXiaomiFamilyDevice(): Boolean {
        val manufacturer = Build.MANUFACTURER.orEmpty().lowercase()
        val brand = Build.BRAND.orEmpty().lowercase()
        return manufacturer in setOf("xiaomi", "redmi", "poco") ||
            brand in setOf("xiaomi", "redmi", "poco")
    }

    private fun cancelSubscription(subscription: Subscription<*>?) {
        if (subscription != null && !subscription.isCanceled) {
            subscription.cancel()
        }
    }

    private fun supportsQueueLookup(contextType: String): Boolean {
        return contextType in setOf("playlist", "album", "artist", "show", "collection")
    }

    private fun inferSpotifyType(uri: String): String {
        return uri.split(':').getOrNull(1).orEmpty()
    }

    private fun extractSpotifyId(uri: String): String {
        return uri.split(':').getOrNull(2)?.takeIf { it.isNotBlank() } ?: uri
    }

    private fun toSpotifyUrl(uri: String): String {
        val type = inferSpotifyType(uri)
        val id = extractSpotifyId(uri)
        if (type.isBlank() || id.isBlank() || id == uri) {
            return ""
        }
        return "https://open.spotify.com/$type/$id"
    }

    private fun sendEvent(payload: HashMap<String, Any?>) {
        runOnUiThread {
            eventSink?.success(payload)
        }
    }
}
