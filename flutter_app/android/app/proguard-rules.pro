# The Spotify App Remote SDK references Jackson and an internal
# annotation class that aren't shipped in the AAR; they're only used
# on code paths this app doesn't exercise, so R8 can be told to ignore them.
-dontwarn com.fasterxml.jackson.databind.deser.std.StdDeserializer
-dontwarn com.fasterxml.jackson.databind.ser.std.StdSerializer
-dontwarn com.spotify.base.annotations.NotNull
