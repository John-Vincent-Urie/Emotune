import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../../providers/auth_provider.dart';
import '../../services/api_service.dart';
import '../../widgets/emotune_backdrop.dart';
import '../../widgets/emotune_buttons.dart';
import '../../widgets/emotune_logo.dart';
import '../../theme/app_theme.dart';
import '../legal/legal_screen.dart';

/// Widest the form is allowed to get. Past this a single column of inputs
/// stretches into an unreadable line on tablets and desktop windows.
const double _kFormMaxWidth = 440;

/// Material's minimum comfortable touch target.
const double _kMinTapTarget = 48;

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  final _emailFocus = FocusNode();
  final _passFocus = FocusNode();
  bool _obscure = true;

  @override
  void initState() {
    super.initState();
    // The submit button tracks the fields, so it can stay disabled until
    // there is actually something to submit.
    _emailCtrl.addListener(_onFormChanged);
    _passCtrl.addListener(_onFormChanged);
    _clearStaleAuthError(this);
  }

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passCtrl.dispose();
    _emailFocus.dispose();
    _passFocus.dispose();
    super.dispose();
  }

  void _onFormChanged() {
    context.read<AuthProvider>().clearError();
    setState(() {});
  }

  bool get _canSubmit =>
      _emailCtrl.text.trim().isNotEmpty && _passCtrl.text.isNotEmpty;

  /// Hands the reset flow whatever address is already typed, so the common
  /// case -- right email, forgotten password -- costs no retyping.
  Future<void> _forgotPassword() async {
    final resetEmail = await Navigator.push<String>(
      context,
      MaterialPageRoute(
        builder: (_) => ForgotPasswordScreen(
          initialEmail: _emailCtrl.text.trim(),
        ),
      ),
    );
    if (!mounted || resetEmail == null) return;

    // Came back from a finished reset: put them on the field they still have
    // to fill, with the address they just proved they own already in place.
    _emailCtrl.text = resetEmail;
    _passCtrl.clear();
    _passFocus.requestFocus();
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Password updated. Log in with it now.')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();

    return _AuthScaffold(
      title: 'Welcome back',
      subtitle: 'Log in to pick up your listening where you left off.',
      logoSize: 88,
      error: auth.error,
      onDismissError: auth.clearError,
      footer: _SwitchAuthLink(
        prompt: "Don't have an account?",
        actionLabel: 'Create one',
        onPressed: auth.isLoading
            ? null
            : () => Navigator.pushReplacementNamed(context, '/register'),
      ),
      child: Form(
        key: _formKey,
        child: AutofillGroup(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _AuthField(
                label: 'Email',
                hint: 'name@example.com',
                controller: _emailCtrl,
                focusNode: _emailFocus,
                enabled: !auth.isLoading,
                keyboardType: TextInputType.emailAddress,
                textInputAction: TextInputAction.next,
                autofillHints: const [AutofillHints.email],
                validator: _validateEmail,
                onSubmitted: (_) => _passFocus.requestFocus(),
              ),
              _AuthField(
                label: 'Password',
                hint: 'Your password',
                controller: _passCtrl,
                focusNode: _passFocus,
                enabled: !auth.isLoading,
                obscure: _obscure,
                onToggleObscure: () => setState(() => _obscure = !_obscure),
                textInputAction: TextInputAction.done,
                autofillHints: const [AutofillHints.password],
                validator: (value) => (value == null || value.isEmpty)
                    ? 'Enter your password'
                    : null,
                onSubmitted: (_) => _submit(),
              ),
              // Sits with the password field rather than below the button:
              // it is a way out of that field, not a second submit action.
              Align(
                alignment: Alignment.centerRight,
                child: ConstrainedBox(
                  constraints:
                      const BoxConstraints(minHeight: _kMinTapTarget),
                  child: TextButton(
                    onPressed: auth.isLoading ? null : _forgotPassword,
                    style: TextButton.styleFrom(
                      foregroundColor: AppColors.accent,
                      padding: const EdgeInsets.symmetric(horizontal: 10),
                      textStyle: const TextStyle(
                        fontSize: 13.5,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    child: const Text('Forgot password?'),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              EmoTunePrimaryButton(
                label: 'Log in',
                isLoading: auth.isLoading,
                onPressed: _canSubmit ? _submit : null,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!(_formKey.currentState?.validate() ?? false)) {
      // Validation already marked the offending field; a failed submit should
      // still register as a distinct event rather than nothing happening.
      HapticFeedback.lightImpact();
      return;
    }

    final auth = context.read<AuthProvider>();
    final success = await auth.login(_emailCtrl.text.trim(), _passCtrl.text);
    if (!mounted) return;
    if (success) {
      TextInput.finishAutofillContext();
      Navigator.pushNamedAndRemoveUntil(context, '/home', (route) => false);
    }
  }
}

// =============== REGISTER SCREEN ===============

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _usernameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  final _confirmCtrl = TextEditingController();
  final _usernameFocus = FocusNode();
  final _emailFocus = FocusNode();
  final _passFocus = FocusNode();
  final _confirmFocus = FocusNode();
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;
  bool _acceptTerms = false;
  bool _personalizationOptIn = true;

  @override
  void initState() {
    super.initState();
    for (final controller in [
      _usernameCtrl,
      _emailCtrl,
      _passCtrl,
      _confirmCtrl,
    ]) {
      controller.addListener(_onFormChanged);
    }
    _clearStaleAuthError(this);
  }

  @override
  void dispose() {
    _usernameCtrl.dispose();
    _emailCtrl.dispose();
    _passCtrl.dispose();
    _confirmCtrl.dispose();
    _usernameFocus.dispose();
    _emailFocus.dispose();
    _passFocus.dispose();
    _confirmFocus.dispose();
    super.dispose();
  }

  void _onFormChanged() {
    context.read<AuthProvider>().clearError();
    setState(() {});
  }

  bool get _canSubmit =>
      _usernameCtrl.text.trim().isNotEmpty &&
      _emailCtrl.text.trim().isNotEmpty &&
      _passCtrl.text.isNotEmpty &&
      _confirmCtrl.text.isNotEmpty &&
      _acceptTerms;

  bool get _passwordsMatch =>
      _confirmCtrl.text.isNotEmpty && _confirmCtrl.text == _passCtrl.text;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();

    return _AuthScaffold(
      title: 'Create your account',
      subtitle:
          'We only ask for the basics here. You can tune personalization later.',
      logoSize: 76,
      error: auth.error,
      onDismissError: auth.clearError,
      footer: _SwitchAuthLink(
        prompt: 'Already have an account?',
        actionLabel: 'Log in',
        onPressed: auth.isLoading
            ? null
            : () => Navigator.pushReplacementNamed(context, '/login'),
      ),
      child: Form(
        key: _formKey,
        child: AutofillGroup(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _AuthField(
                label: 'Display name',
                hint: 'How should EmoTune address you?',
                controller: _usernameCtrl,
                focusNode: _usernameFocus,
                enabled: !auth.isLoading,
                textCapitalization: TextCapitalization.words,
                textInputAction: TextInputAction.next,
                autofillHints: const [AutofillHints.newUsername],
                validator: (value) => (value == null || value.trim().isEmpty)
                    ? 'Display name is required'
                    : null,
                onSubmitted: (_) => _emailFocus.requestFocus(),
              ),
              _AuthField(
                label: 'Email',
                hint: 'name@example.com',
                controller: _emailCtrl,
                focusNode: _emailFocus,
                enabled: !auth.isLoading,
                keyboardType: TextInputType.emailAddress,
                textInputAction: TextInputAction.next,
                autofillHints: const [AutofillHints.email],
                validator: _validateEmail,
                onSubmitted: (_) => _passFocus.requestFocus(),
              ),
              _AuthField(
                label: 'Password',
                hint: 'At least 8 characters',
                controller: _passCtrl,
                focusNode: _passFocus,
                enabled: !auth.isLoading,
                obscure: _obscurePassword,
                onToggleObscure: () =>
                    setState(() => _obscurePassword = !_obscurePassword),
                textInputAction: TextInputAction.next,
                autofillHints: const [AutofillHints.newPassword],
                validator: _validatePassword,
                onSubmitted: (_) => _confirmFocus.requestFocus(),
              ),
              _PasswordStrengthMeter(password: _passCtrl.text),
              const SizedBox(height: 18),
              _AuthField(
                label: 'Confirm password',
                hint: 'Repeat your password',
                controller: _confirmCtrl,
                focusNode: _confirmFocus,
                enabled: !auth.isLoading,
                obscure: _obscureConfirmPassword,
                onToggleObscure: () => setState(
                  () => _obscureConfirmPassword = !_obscureConfirmPassword,
                ),
                textInputAction: TextInputAction.done,
                autofillHints: const [AutofillHints.newPassword],
                // The tick is the reward for getting it right, shown the
                // moment it matches instead of waiting for a failed submit.
                showMatchTick: _passwordsMatch,
                validator: (value) => (value != _passCtrl.text)
                    ? 'Passwords do not match'
                    : null,
                onSubmitted: (_) => _submit(),
              ),
              const SizedBox(height: 2),
              _ConsentTile(
                title: 'I agree to the Terms and Privacy Policy',
                subtitle: 'Required so we can create and protect your account.',
                value: _acceptTerms,
                enabled: !auth.isLoading,
                isRequired: true,
                onChanged: (value) => setState(() => _acceptTerms = value),
              ),
              // Outside the tile: a link inside it would also toggle the box.
              // A Wrap, so the second link drops to its own line on a narrow
              // phone instead of overflowing.
              Wrap(
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  _LegalLink(
                    label: 'Read the Terms',
                    onTap: () => LegalScreen.open(context, LegalDoc.terms),
                  ),
                  Text(
                    '·',
                    style: TextStyle(color: Colors.white.withValues(alpha: 0.5)),
                  ),
                  _LegalLink(
                    label: 'Read the Privacy Policy',
                    onTap: () => LegalScreen.open(context, LegalDoc.privacy),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              _ConsentTile(
                title: 'Use my mood activity to personalize recommendations',
                subtitle:
                    'Optional. You can turn this off later for more private sessions.',
                value: _personalizationOptIn,
                enabled: !auth.isLoading,
                onChanged: (value) =>
                    setState(() => _personalizationOptIn = value),
              ),
              const SizedBox(height: 28),
              EmoTunePrimaryButton(
                label: 'Create account',
                isLoading: auth.isLoading,
                onPressed: _canSubmit ? _submit : null,
              ),
              const SizedBox(height: 12),
              // The button goes dim before the form is complete, so say why
              // rather than leaving the user tapping a dead control.
              AnimatedOpacity(
                opacity: _canSubmit ? 0 : 1,
                duration: const Duration(milliseconds: 180),
                child: Text(
                  _acceptTerms
                      ? 'Fill in every field to continue.'
                      : 'Agree to the Terms and Privacy Policy to continue.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.5),
                    fontSize: 12,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!(_formKey.currentState?.validate() ?? false)) {
      HapticFeedback.lightImpact();
      return;
    }
    if (!_acceptTerms) {
      HapticFeedback.lightImpact();
      return;
    }

    final auth = context.read<AuthProvider>();
    final success = await auth.register(
      _usernameCtrl.text.trim(),
      _emailCtrl.text.trim(),
      _passCtrl.text,
      acceptTerms: _acceptTerms,
      personalizationOptIn: _personalizationOptIn,
    );
    if (!mounted) return;
    if (success) {
      TextInput.finishAutofillContext();
      Navigator.pushNamedAndRemoveUntil(context, '/home', (route) => false);
    }
  }
}

// =============== SHARED VALIDATION ===============

String? _validateEmail(String? value) {
  final email = (value ?? '').trim();
  if (email.isEmpty) return 'Email is required';
  // Deliberately loose: the server is the authority on deliverability, this
  // only catches the obvious typo before a round trip.
  if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email)) {
    return 'Enter a valid email address';
  }
  return null;
}

/// Login and Register share AuthProvider.error, so a failed sign-in banner
/// followed the user onto Register. Each screen starts clean. After the first
/// frame, because clearing notifies listeners and must not run mid-build.
void _clearStaleAuthError(State state) {
  WidgetsBinding.instance.addPostFrameCallback((_) {
    if (state.mounted) state.context.read<AuthProvider>().clearError();
  });
}

String? _validatePassword(String? value) {
  final password = value ?? '';
  if (password.isEmpty) return 'Password is required';
  // Mirrors the server's validators that can be checked on the device, so
  // the rule is never a surprise. "Too common" and "too similar to your
  // email" are server-only and come back in the error banner.
  if (password.length < 8) return 'Use at least 8 characters';
  if (RegExp(r'^\d+$').hasMatch(password)) {
    return 'Add a letter or symbol, not only numbers';
  }
  return null;
}

// =============== SHARED LAYOUT ===============

/// The frame both auth screens share: one column, one job, capped width.
class _AuthScaffold extends StatelessWidget {
  const _AuthScaffold({
    required this.title,
    required this.subtitle,
    required this.child,
    required this.footer,
    required this.logoSize,
    this.error,
    this.onDismissError,
  });

  final String title;
  final String subtitle;
  final Widget child;
  final Widget footer;
  final double logoSize;
  final String? error;
  final VoidCallback? onDismissError;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.darkBg,
      body: Stack(
        children: [
          const Positioned.fill(child: EmoTuneBackdrop()),
          SafeArea(
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: _kFormMaxWidth),
                child: GestureDetector(
                  // Tapping the background dismisses the keyboard, the standard
                  // escape hatch on a form this tall.
                  onTap: () => FocusScope.of(context).unfocus(),
                  behavior: HitTestBehavior.opaque,
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Align(
                          alignment: Alignment.centerLeft,
                          child: IconButton(
                            icon: const Icon(Icons.arrow_back),
                            color: AppColors.accent,
                            tooltip: 'Back',
                            // After a session expiry the route stack was
                            // cleared, so there is nothing to pop back to.
                            onPressed: () => Navigator.canPop(context)
                                ? Navigator.pop(context)
                                : Navigator.pushReplacementNamed(
                                    context,
                                    '/welcome',
                                  ),
                          ),
                        ),
                        const SizedBox(height: 4),
                        EmoTuneLogo(size: logoSize),
                        const SizedBox(height: 28),
                        Semantics(
                          header: true,
                          child: Text(
                            title,
                            style: emoTuneHeadlineFont(
                              fontSize: 26,
                              fontWeight: FontWeight.w600,
                              color: Colors.white,
                              height: 1.2,
                            ),
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          subtitle,
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.66),
                            fontSize: 13.5,
                            height: 1.45,
                          ),
                        ),
                        const SizedBox(height: 24),
                        child,
                        // Below the form rather than above it: shown above, a
                        // failed submit pushed the button ~80px down, right
                        // under a second tap. Here it lands next to the button
                        // the user just pressed and nothing above it moves.
                        _ErrorBanner(message: error, onDismiss: onDismissError),
                        const SizedBox(height: 24),
                        footer,
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// A server-side failure, announced rather than silently swapped in.
class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message, this.onDismiss});

  final String? message;
  final VoidCallback? onDismiss;

  @override
  Widget build(BuildContext context) {
    const errorColor = Color(0xFFFF6B6B);

    return AnimatedSize(
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOutCubic,
      alignment: Alignment.topCenter,
      child: AnimatedSwitcher(
        duration: const Duration(milliseconds: 220),
        child: message == null
            ? const SizedBox(width: double.infinity)
            : Semantics(
                liveRegion: true,
                container: true,
                child: Container(
                  key: ValueKey(message),
                  width: double.infinity,
                  padding: const EdgeInsets.fromLTRB(14, 12, 6, 12),
                  margin: const EdgeInsets.only(top: 16),
                  decoration: BoxDecoration(
                    color: errorColor.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: errorColor.withValues(alpha: 0.4)),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(
                        Icons.error_outline,
                        color: errorColor,
                        size: 20,
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          message!,
                          style: const TextStyle(
                            color: errorColor,
                            fontSize: 13,
                            height: 1.35,
                          ),
                        ),
                      ),
                      if (onDismiss != null)
                        IconButton(
                          icon: const Icon(Icons.close, size: 18),
                          color: errorColor.withValues(alpha: 0.8),
                          tooltip: 'Dismiss',
                          visualDensity: VisualDensity.compact,
                          onPressed: onDismiss,
                        ),
                    ],
                  ),
                ),
              ),
      ),
    );
  }
}

/// A labelled text field that reacts to focus, so the caret is never the only
/// thing telling the user where they are.
class _AuthField extends StatefulWidget {
  const _AuthField({
    required this.label,
    required this.controller,
    required this.focusNode,
    this.hint,
    this.enabled = true,
    this.obscure = false,
    this.onToggleObscure,
    this.keyboardType,
    this.textInputAction,
    this.textCapitalization = TextCapitalization.none,
    this.autofillHints,
    this.validator,
    this.onSubmitted,
    this.showMatchTick = false,
  });

  final String label;
  final String? hint;
  final TextEditingController controller;
  final FocusNode focusNode;
  final bool enabled;
  final bool obscure;
  final VoidCallback? onToggleObscure;
  final TextInputType? keyboardType;
  final TextInputAction? textInputAction;
  final TextCapitalization textCapitalization;
  final Iterable<String>? autofillHints;
  final FormFieldValidator<String>? validator;
  final ValueChanged<String>? onSubmitted;
  final bool showMatchTick;

  @override
  State<_AuthField> createState() => _AuthFieldState();
}

class _AuthFieldState extends State<_AuthField> {
  final _fieldKey = GlobalKey<FormFieldState<String>>();
  bool _focused = false;
  // Typed in at least once. A field the user only tabbed through is not
  // flagged on blur; submit still validates it.
  bool _dirty = false;
  // Validating from the first keystroke shouted "Enter a valid email" at
  // "j". Errors now wait for the user to leave the field (or submit), and
  // once shown they track every keystroke so a fix clears them at once.
  bool _liveValidation = false;

  @override
  void initState() {
    super.initState();
    widget.focusNode.addListener(_onFocusChanged);
  }

  @override
  void dispose() {
    widget.focusNode.removeListener(_onFocusChanged);
    super.dispose();
  }

  void _onFocusChanged() {
    if (!mounted) return;
    setState(() {
      _focused = widget.focusNode.hasFocus;
      if (!_focused && _dirty) _liveValidation = true;
    });
  }

  void _onChanged(String _) {
    _dirty = true;
    // After a failed submit the error is on screen but live validation is
    // not on yet; without this it would sit there stale until the next submit.
    if (!_liveValidation && (_fieldKey.currentState?.hasError ?? false)) {
      setState(() => _liveValidation = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isPassword = widget.onToggleObscure != null;

    // Merged so the field is announced by its visible label ("Email, edit
    // box"), not only by its hint text.
    return MergeSemantics(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // The label brightens with focus: a second, non-color-only cue that
          // pairs with the border so it reads without relying on hue alone.
          AnimatedDefaultTextStyle(
            duration: const Duration(milliseconds: 160),
            style: TextStyle(
              color: _focused
                  ? AppColors.accent
                  : Colors.white.withValues(alpha: 0.72),
              fontSize: 13,
              fontWeight: _focused ? FontWeight.w600 : FontWeight.w500,
              letterSpacing: 0.2,
            ),
            child: Text(widget.label),
          ),
          const SizedBox(height: 7),
          AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOut,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              boxShadow: _focused
                  ? [
                      BoxShadow(
                        color: AppColors.accent.withValues(alpha: 0.18),
                        blurRadius: 14,
                        spreadRadius: 1,
                      ),
                    ]
                  : const [],
            ),
            child: TextFormField(
              key: _fieldKey,
              autovalidateMode: _liveValidation
                  ? AutovalidateMode.always
                  : AutovalidateMode.disabled,
              onChanged: _onChanged,
              controller: widget.controller,
              focusNode: widget.focusNode,
              enabled: widget.enabled,
              obscureText: widget.obscure,
              keyboardType: widget.keyboardType,
              textInputAction: widget.textInputAction,
              textCapitalization: widget.textCapitalization,
              autofillHints: widget.autofillHints,
              validator: widget.validator,
              onFieldSubmitted: widget.onSubmitted,
              // Email and password fields should never be "helpfully" corrected.
              autocorrect: !isPassword && widget.keyboardType == null,
              enableSuggestions: !isPassword,
              style: const TextStyle(color: Colors.white, fontSize: 15),
              cursorColor: AppColors.accent,
              decoration: InputDecoration(
                hintText: widget.hint,
                hintStyle: TextStyle(
                  color: Colors.white.withValues(alpha: 0.32),
                  fontSize: 14,
                ),
                filled: true,
                fillColor: widget.enabled
                    ? AppColors.darkCard
                    : AppColors.darkCard.withValues(alpha: 0.5),
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                border: _border(AppColors.darkBorder),
                enabledBorder: _border(AppColors.darkBorder),
                disabledBorder: _border(AppColors.darkBorder),
                focusedBorder: _border(AppColors.accent, width: 1.6),
                errorBorder: _border(const Color(0xFFFF6B6B)),
                focusedErrorBorder:
                    _border(const Color(0xFFFF6B6B), width: 1.6),
                errorStyle: const TextStyle(
                  color: Color(0xFFFF6B6B),
                  fontSize: 12,
                ),
                // A blank helper line holds the error's slot open, so an error
                // appearing or clearing moves nothing below the field. The gaps
                // between fields were cut by the same amount.
                helperText: ' ',
                helperStyle: const TextStyle(fontSize: 12),
                errorMaxLines: 2,
                suffixIcon: _buildSuffix(isPassword),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget? _buildSuffix(bool isPassword) {
    if (isPassword) {
      return IconButton(
        icon: Icon(
          widget.obscure ? Icons.visibility_off : Icons.visibility,
          size: 20,
        ),
        color: Colors.white.withValues(alpha: 0.5),
        tooltip: widget.obscure ? 'Show password' : 'Hide password',
        onPressed: widget.enabled ? widget.onToggleObscure : null,
      );
    }
    if (widget.showMatchTick) {
      return const Icon(Icons.check_circle, color: AppColors.accent, size: 20);
    }
    return null;
  }

  OutlineInputBorder _border(Color color, {double width = 1}) {
    return OutlineInputBorder(
      borderRadius: BorderRadius.circular(12),
      borderSide: BorderSide(color: color, width: width),
    );
  }
}

/// Live feedback on the password as it is typed, so the rule is discovered
/// while typing rather than on a rejected submit.
class _PasswordStrengthMeter extends StatelessWidget {
  const _PasswordStrengthMeter({required this.password});

  final String password;

  /// 0 = too short, 1 = weak, 2 = fair, 3 = strong.
  int get _score {
    if (password.length < 8) return 0;
    var score = 1;
    if (password.length >= 12) score++;
    final hasLetters = RegExp(r'[A-Za-z]').hasMatch(password);
    final hasDigits = RegExp(r'\d').hasMatch(password);
    final hasSymbols = RegExp(r'[^A-Za-z0-9]').hasMatch(password);
    if ([hasLetters, hasDigits, hasSymbols].where((has) => has).length >= 3) {
      score++;
    }
    return score.clamp(0, 3);
  }

  @override
  Widget build(BuildContext context) {
    const labels = ['Too short', 'Weak', 'Fair', 'Strong'];
    const colors = [
      Color(0xFFFF6B6B),
      Color(0xFFFFB84D),
      Color(0xFFDDFF7E),
      AppColors.accent,
    ];
    final score = _score;

    // Hidden rather than removed while the field is empty, so its first
    // keystroke doesn't shove every field and the button below it down.
    return AnimatedOpacity(
      opacity: password.isEmpty ? 0 : 1,
      duration: const Duration(milliseconds: 180),
      child: Padding(
        // The field's reserved error line above already spaces it.
        padding: const EdgeInsets.only(top: 2),
        child: Row(
          children: [
            for (var index = 0; index < 3; index++) ...[
              Expanded(
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 220),
                  curve: Curves.easeOut,
                  height: 4,
                  decoration: BoxDecoration(
                    color: index < score
                        ? colors[score]
                        : Colors.white.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              if (index < 2) const SizedBox(width: 6),
            ],
            const SizedBox(width: 12),
            // The bars carry the same meaning as the word, so a viewer who
            // cannot separate the colors still gets the verdict.
            SizedBox(
              width: 66,
              child: Text(
                labels[score],
                textAlign: TextAlign.right,
                style: TextStyle(
                  color: colors[score],
                  fontSize: 11.5,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LegalLink extends StatelessWidget {
  const _LegalLink({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: onTap,
      style: TextButton.styleFrom(
        foregroundColor: AppColors.accent,
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
        // A full 48dp target; QA measured the old ones under 48 tall. Standard
        // density, or web/desktop's compact default shrinks the minimum.
        minimumSize: const Size(48, 48),
        tapTargetSize: MaterialTapTargetSize.padded,
        visualDensity: VisualDensity.standard,
        textStyle: const TextStyle(
          fontSize: 13.5,
          fontWeight: FontWeight.w600,
          decoration: TextDecoration.underline,
        ),
      ),
      child: Text(label),
    );
  }
}

/// A consent row where the whole card is the target, not just the checkbox.
class _ConsentTile extends StatelessWidget {
  const _ConsentTile({
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
    this.enabled = true,
    this.isRequired = false,
  });

  final String title;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;
  final bool enabled;
  final bool isRequired;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 180),
      decoration: BoxDecoration(
        color: value
            ? AppColors.accent.withValues(alpha: 0.06)
            : const Color(0xFF141414),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: value
              ? AppColors.accent.withValues(alpha: 0.45)
              : AppColors.darkBorder,
        ),
      ),
      child: Semantics(
        // The checkbox itself is excluded below, so the tile carries the
        // checked state; before, TalkBack never said whether it was ticked.
        checked: value,
        enabled: enabled,
        child: Material(
          color: Colors.transparent,
          borderRadius: BorderRadius.circular(14),
          child: InkWell(
            borderRadius: BorderRadius.circular(14),
            onTap: enabled ? () => onChanged(!value) : null,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 12, 14, 12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Excluded from semantics because the InkWell above already
                  // exposes one checkbox; two would be read out twice.
                  ExcludeSemantics(
                    child: SizedBox(
                      width: 24,
                      height: 24,
                      child: Checkbox(
                        value: value,
                        activeColor: AppColors.accent,
                        checkColor: Colors.black,
                        side: BorderSide(
                          color: Colors.white.withValues(alpha: 0.4),
                        ),
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        onChanged:
                            enabled ? (next) => onChanged(next ?? false) : null,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Flexible(
                              child: Text(
                                title,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  height: 1.3,
                                ),
                              ),
                            ),
                            if (isRequired) ...[
                              const SizedBox(width: 6),
                              const _RequiredChip(),
                            ],
                          ],
                        ),
                        const SizedBox(height: 3),
                        Text(
                          subtitle,
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.6),
                            fontSize: 12,
                            height: 1.35,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _RequiredChip extends StatelessWidget {
  const _RequiredChip();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(5),
      ),
      child: Text(
        'Required',
        style: TextStyle(
          color: Colors.white.withValues(alpha: 0.66),
          fontSize: 10,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.3,
        ),
      ),
    );
  }
}

/// The way out of a dead end: each auth screen points at the other one.
class _SwitchAuthLink extends StatelessWidget {
  const _SwitchAuthLink({
    required this.prompt,
    required this.actionLabel,
    required this.onPressed,
  });

  final String prompt;
  final String actionLabel;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    // Wrap, not Row: at a large text scale or on a narrow phone the prompt and
    // the action need to fall onto two lines instead of overflowing.
    return Wrap(
      alignment: WrapAlignment.center,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        Text(
          prompt,
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.6),
            fontSize: 13.5,
          ),
        ),
        const SizedBox(width: 4),
        ConstrainedBox(
          constraints: const BoxConstraints(minHeight: _kMinTapTarget),
          child: TextButton(
            onPressed: onPressed,
            style: TextButton.styleFrom(
              foregroundColor: AppColors.accent,
              padding: const EdgeInsets.symmetric(horizontal: 10),
              textStyle: const TextStyle(
                fontSize: 13.5,
                fontWeight: FontWeight.w700,
              ),
            ),
            child: Text(actionLabel),
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Forgotten password: email a one-time code, verify it, choose a new password
// ---------------------------------------------------------------------------

enum _ResetStep { email, code, password, done }

/// Three steps behind one back button. Splitting them across routes would let
/// the user walk backwards into a step whose code has already been spent, so
/// the flow advances in place and only ever offers the way forward.
class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({super.key, this.initialEmail = ''});

  /// Prefilled from the login form when the user came from there.
  final String initialEmail;

  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> {
  /// Long enough that a slow mail hop lands first, short enough not to strand
  /// anyone whose code genuinely never arrives.
  static const int _resendCooldownSeconds = 60;
  static const int _codeLength = 6;

  final _emailCtrl = TextEditingController();
  final _codeCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  final _confirmCtrl = TextEditingController();

  final _emailFocus = FocusNode();
  final _codeFocus = FocusNode();
  final _passFocus = FocusNode();
  final _confirmFocus = FocusNode();

  _ResetStep _step = _ResetStep.email;
  bool _busy = false;
  String? _error;
  bool _obscure = true;
  int _resendIn = 0;
  Timer? _resendTimer;

  @override
  void initState() {
    super.initState();
    _emailCtrl.text = widget.initialEmail;
    for (final controller in [_emailCtrl, _codeCtrl, _passCtrl, _confirmCtrl]) {
      controller.addListener(_onTyping);
    }
  }

  @override
  void dispose() {
    _resendTimer?.cancel();
    for (final controller in [_emailCtrl, _codeCtrl, _passCtrl, _confirmCtrl]) {
      controller.dispose();
    }
    for (final node in [_emailFocus, _codeFocus, _passFocus, _confirmFocus]) {
      node.dispose();
    }
    super.dispose();
  }

  void _onTyping() {
    // Buttons track the fields, and a stale error under a field the user has
    // already corrected is just noise.
    setState(() => _error = null);
  }

  bool get _emailLooksValid => _validateEmail(_emailCtrl.text) == null;
  bool get _codeComplete => _codeCtrl.text.length == _codeLength;
  bool get _passwordsReady =>
      _validatePassword(_passCtrl.text) == null &&
      _passCtrl.text == _confirmCtrl.text;

  String get _email => _emailCtrl.text.trim().toLowerCase();

  void _startResendCooldown() {
    _resendTimer?.cancel();
    setState(() => _resendIn = _resendCooldownSeconds);
    _resendTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }
      setState(() => _resendIn -= 1);
      if (_resendIn <= 0) timer.cancel();
    });
  }

  /// Every step is the same shape: disable the form, call, show what broke.
  Future<void> _run(Future<void> Function() action) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Could not reach EmoTune. Check your connection.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _sendCode({bool resending = false}) {
    return _run(() async {
      await ApiService.requestPasswordReset(_email);
      if (!mounted) return;
      setState(() {
        _step = _ResetStep.code;
        if (resending) _codeCtrl.clear();
      });
      _startResendCooldown();
      _codeFocus.requestFocus();
      if (resending) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('A new code is on its way.')),
        );
      }
    });
  }

  Future<void> _verifyCode() async {
    int? rejectedWith;
    await _run(() async {
      try {
        await ApiService.verifyPasswordResetCode(_email, _codeCtrl.text);
      } on ApiException catch (e) {
        rejectedWith = e.statusCode;
        rethrow;
      }
      if (!mounted) return;
      setState(() => _step = _ResetStep.password);
      _passFocus.requestFocus();
    });
    // A rejected code left all six boxes full, so typing the right one meant
    // deleting six digits first. Only on a real rejection: after a network
    // error or a throttle the code may well be right.
    final status = rejectedWith;
    if (mounted &&
        status != null &&
        status >= 400 &&
        status < 500 &&
        status != 429) {
      // clear() fires _onTyping, which wipes _error -- the code vanished with
      // no explanation. Put the server's message back after clearing.
      final message = _error;
      _codeCtrl.clear();
      setState(() => _error = message);
      _codeFocus.requestFocus();
    }
  }

  Future<void> _resetPassword() {
    return _run(() async {
      await ApiService.confirmPasswordReset(
        _email,
        _codeCtrl.text,
        _passCtrl.text,
      );
      if (!mounted) return;
      _resendTimer?.cancel();
      setState(() => _step = _ResetStep.done);
    });
  }

  @override
  Widget build(BuildContext context) {
    return _AuthScaffold(
      title: _title,
      subtitle: _subtitle,
      logoSize: 72,
      error: _error,
      onDismissError: () => setState(() => _error = null),
      footer: _footer(),
      child: AnimatedSize(
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOut,
        alignment: Alignment.topCenter,
        child: AnimatedSwitcher(
          duration: const Duration(milliseconds: 220),
          child: KeyedSubtree(
            key: ValueKey(_step),
            child: _stepBody(),
          ),
        ),
      ),
    );
  }

  String get _title {
    switch (_step) {
      case _ResetStep.email:
        return 'Forgot password';
      case _ResetStep.code:
        return 'Check your email';
      case _ResetStep.password:
        return 'Choose a new password';
      case _ResetStep.done:
        return 'Password updated';
    }
  }

  String get _subtitle {
    switch (_step) {
      case _ResetStep.email:
        return 'Enter the email on your account and we will send you a '
            '$_codeLength-digit code.';
      case _ResetStep.code:
        return 'We sent a $_codeLength-digit code to $_email. It expires in a '
            'few minutes.';
      case _ResetStep.password:
        return 'Code confirmed. Pick a password you have not used here before.';
      case _ResetStep.done:
        return 'You can log in with your new password now.';
    }
  }

  Widget _stepBody() {
    switch (_step) {
      case _ResetStep.email:
        return _emailStep();
      case _ResetStep.code:
        return _codeStep();
      case _ResetStep.password:
        return _passwordStep();
      case _ResetStep.done:
        return _doneStep();
    }
  }

  Widget _emailStep() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _AuthField(
          label: 'Email',
          hint: 'name@example.com',
          controller: _emailCtrl,
          focusNode: _emailFocus,
          enabled: !_busy,
          keyboardType: TextInputType.emailAddress,
          textInputAction: TextInputAction.done,
          autofillHints: const [AutofillHints.email],
          validator: _validateEmail,
          onSubmitted: (_) => _emailLooksValid ? _sendCode() : null,
        ),
        const SizedBox(height: 8),
        EmoTunePrimaryButton(
          label: 'Send code',
          isLoading: _busy,
          onPressed: _emailLooksValid ? _sendCode : null,
        ),
      ],
    );
  }

  Widget _codeStep() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _OtpField(
          controller: _codeCtrl,
          focusNode: _codeFocus,
          length: _codeLength,
          enabled: !_busy,
          // Verifying the moment the last digit lands saves a tap; the button
          // stays for anyone who pastes or edits their way to six digits.
          onCompleted: _verifyCode,
        ),
        const SizedBox(height: 20),
        EmoTunePrimaryButton(
          label: 'Verify code',
          isLoading: _busy,
          onPressed: _codeComplete ? _verifyCode : null,
        ),
        const SizedBox(height: 6),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ConstrainedBox(
              constraints: const BoxConstraints(minHeight: _kMinTapTarget),
              child: TextButton(
                onPressed:
                    _busy || _resendIn > 0 ? null : () => _sendCode(resending: true),
                style: TextButton.styleFrom(
                  foregroundColor: AppColors.accent,
                  disabledForegroundColor: Colors.white.withValues(alpha: 0.35),
                ),
                child: Text(
                  _resendIn > 0 ? 'Resend in ${_resendIn}s' : 'Resend code',
                  style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _passwordStep() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _AuthField(
          label: 'New password',
          hint: 'At least 8 characters',
          controller: _passCtrl,
          focusNode: _passFocus,
          enabled: !_busy,
          obscure: _obscure,
          onToggleObscure: () => setState(() => _obscure = !_obscure),
          textInputAction: TextInputAction.next,
          autofillHints: const [AutofillHints.newPassword],
          validator: _validatePassword,
          onSubmitted: (_) => _confirmFocus.requestFocus(),
        ),
        _PasswordStrengthMeter(password: _passCtrl.text),
        const SizedBox(height: 18),
        _AuthField(
          label: 'Confirm new password',
          hint: 'Type it again',
          controller: _confirmCtrl,
          focusNode: _confirmFocus,
          enabled: !_busy,
          obscure: _obscure,
          textInputAction: TextInputAction.done,
          autofillHints: const [AutofillHints.newPassword],
          showMatchTick:
              _confirmCtrl.text.isNotEmpty && _confirmCtrl.text == _passCtrl.text,
          validator: (value) =>
              (value != _passCtrl.text) ? 'Passwords do not match' : null,
          onSubmitted: (_) => _passwordsReady ? _resetPassword() : null,
        ),
        const SizedBox(height: 8),
        EmoTunePrimaryButton(
          label: 'Reset password',
          isLoading: _busy,
          onPressed: _passwordsReady ? _resetPassword : null,
        ),
      ],
    );
  }

  Widget _doneStep() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Icon(Icons.check_circle_outline, color: AppColors.accent, size: 56),
        const SizedBox(height: 24),
        EmoTunePrimaryButton(
          label: 'Back to login',
          isLoading: false,
          // Hands the address back so the login form can prefill it.
          onPressed: () => Navigator.pop(context, _email),
        ),
      ],
    );
  }

  Widget _footer() {
    if (_step == _ResetStep.done) return const SizedBox.shrink();
    if (_step == _ResetStep.code) {
      return _SwitchAuthLink(
        prompt: 'Wrong address?',
        actionLabel: 'Change it',
        onPressed: _busy
            ? null
            : () {
                _resendTimer?.cancel();
                setState(() {
                  _step = _ResetStep.email;
                  _codeCtrl.clear();
                  _resendIn = 0;
                });
                _emailFocus.requestFocus();
              },
      );
    }
    return _SwitchAuthLink(
      prompt: 'Remembered it?',
      actionLabel: 'Log in',
      onPressed: _busy ? null : () => Navigator.pop(context),
    );
  }
}

/// Six boxes that share one hidden text field.
///
/// Six separate fields is the obvious build and the wrong one: it breaks
/// pasting a code, makes backspace ambiguous, and fights autofill. One field
/// behind a painted row keeps all of that working for free.
class _OtpField extends StatefulWidget {
  const _OtpField({
    required this.controller,
    required this.focusNode,
    required this.length,
    required this.onCompleted,
    this.enabled = true,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final int length;
  final VoidCallback onCompleted;
  final bool enabled;

  @override
  State<_OtpField> createState() => _OtpFieldState();
}

class _OtpFieldState extends State<_OtpField> {
  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_onChanged);
    widget.focusNode.addListener(_onFocusChanged);
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onChanged);
    widget.focusNode.removeListener(_onFocusChanged);
    super.dispose();
  }

  void _onFocusChanged() => setState(() {});

  bool _fired = false;

  void _onChanged() {
    setState(() {});
    final complete = widget.controller.text.length == widget.length;
    // Only fire on the transition into completeness, or editing a full code
    // would re-submit on every keystroke.
    if (complete && !_fired) {
      _fired = true;
      widget.focusNode.unfocus();
      widget.onCompleted();
    } else if (!complete) {
      _fired = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final digits = widget.controller.text;
    final cursorAt = digits.length;

    return Stack(
      alignment: Alignment.center,
      children: [
        IgnorePointer(
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              for (var i = 0; i < widget.length; i++)
                _box(
                  digit: i < digits.length ? digits[i] : '',
                  active: widget.focusNode.hasFocus &&
                      (i == cursorAt || (cursorAt == widget.length && i == cursorAt - 1)),
                ),
            ],
          ),
        ),
        // Invisible, but full-width so a tap anywhere on the row opens the
        // keyboard and lands the caret at the end.
        Positioned.fill(
          child: Semantics(
            label: 'Verification code, ${widget.length} digits',
            child: TextField(
              controller: widget.controller,
              focusNode: widget.focusNode,
              enabled: widget.enabled,
              autofocus: true,
              keyboardType: TextInputType.number,
              textInputAction: TextInputAction.done,
              autofillHints: const [AutofillHints.oneTimeCode],
              inputFormatters: [
                FilteringTextInputFormatter.digitsOnly,
                LengthLimitingTextInputFormatter(widget.length),
              ],
              showCursor: false,
              cursorColor: Colors.transparent,
              style: const TextStyle(color: Colors.transparent, fontSize: 1),
              decoration: const InputDecoration(
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                filled: false,
                counterText: '',
                contentPadding: EdgeInsets.zero,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _box({required String digit, required bool active}) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      width: 46,
      height: 58,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: AppColors.darkSurface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: active
              ? AppColors.accent
              : digit.isNotEmpty
                  ? Colors.white.withValues(alpha: 0.28)
                  : AppColors.darkBorder,
          width: active ? 1.6 : 1,
        ),
      ),
      child: Text(
        digit,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 22,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}
