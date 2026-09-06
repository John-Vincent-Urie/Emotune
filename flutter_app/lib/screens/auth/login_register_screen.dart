import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/emotune_logo.dart';
import '../../theme/app_theme.dart';

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
        autovalidateMode: AutovalidateMode.onUserInteraction,
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
              const SizedBox(height: 18),
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
              const SizedBox(height: 28),
              _PrimaryButton(
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
      Navigator.pushReplacementNamed(context, '/home');
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
        autovalidateMode: AutovalidateMode.onUserInteraction,
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
              const SizedBox(height: 18),
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
              const SizedBox(height: 18),
              _AuthField(
                label: 'Password',
                hint: 'At least 6 characters',
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
              const SizedBox(height: 22),
              _ConsentTile(
                title: 'I agree to the Terms and Privacy Policy',
                subtitle: 'Required so we can create and protect your account.',
                value: _acceptTerms,
                enabled: !auth.isLoading,
                isRequired: true,
                onChanged: (value) => setState(() => _acceptTerms = value),
              ),
              const SizedBox(height: 12),
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
              _PrimaryButton(
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
      Navigator.pushReplacementNamed(context, '/home');
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

String? _validatePassword(String? value) {
  final password = value ?? '';
  if (password.isEmpty) return 'Password is required';
  // Matches the server's own minimum so the rule is never a surprise.
  if (password.length < 6) return 'Use at least 6 characters';
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
      body: SafeArea(
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
                        onPressed: () => Navigator.maybePop(context),
                      ),
                    ),
                    const SizedBox(height: 4),
                    EmoTuneLogo(size: logoSize),
                    const SizedBox(height: 28),
                    Semantics(
                      header: true,
                      child: Text(
                        title,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 26,
                          fontWeight: FontWeight.w700,
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
                    _ErrorBanner(message: error, onDismiss: onDismissError),
                    child,
                    const SizedBox(height: 24),
                    footer,
                  ],
                ),
              ),
            ),
          ),
        ),
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
                  margin: const EdgeInsets.only(bottom: 20),
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
  bool _focused = false;

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
    setState(() => _focused = widget.focusNode.hasFocus);
  }

  @override
  Widget build(BuildContext context) {
    final isPassword = widget.onToggleObscure != null;

    return Column(
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
              suffixIcon: _buildSuffix(isPassword),
            ),
          ),
        ),
      ],
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
    if (password.length < 6) return 0;
    var score = 1;
    if (password.length >= 10) score++;
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
    if (password.isEmpty) return const SizedBox.shrink();

    const labels = ['Too short', 'Weak', 'Fair', 'Strong'];
    const colors = [
      Color(0xFFFF6B6B),
      Color(0xFFFFB84D),
      Color(0xFFDDFF7E),
      AppColors.accent,
    ];
    final score = _score;

    return Padding(
      padding: const EdgeInsets.only(top: 10),
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

/// Full-width submit button that keeps its height while it swaps in a spinner,
/// so the layout never jumps at the moment the user is waiting on it.
class _PrimaryButton extends StatelessWidget {
  const _PrimaryButton({
    required this.label,
    required this.isLoading,
    required this.onPressed,
  });

  final String label;
  final bool isLoading;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 54,
      child: ElevatedButton(
        onPressed: isLoading ? null : onPressed,
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.accent,
          foregroundColor: Colors.black,
          disabledBackgroundColor: AppColors.accent.withValues(alpha: 0.28),
          disabledForegroundColor: Colors.black.withValues(alpha: 0.45),
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(30),
          ),
        ),
        child: AnimatedSwitcher(
          duration: const Duration(milliseconds: 180),
          child: isLoading
              ? const SizedBox(
                  key: ValueKey('loading'),
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(
                    strokeWidth: 2.4,
                    valueColor: AlwaysStoppedAnimation(Colors.black),
                  ),
                )
              : Text(
                  label,
                  key: const ValueKey('label'),
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                  ),
                ),
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
