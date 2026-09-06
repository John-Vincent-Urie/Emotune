import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class EmoTuneLogo extends StatelessWidget {
  final double size;
  final bool showText;

  const EmoTuneLogo({super.key, this.size = 100, this.showText = true});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [Color(0xFF7EFFD4), Color(0xFF89E0FF), Color(0xFFDDFF7E)],
            ),
            boxShadow: [
              BoxShadow(
                color: AppColors.gradientStart.withValues(alpha: 0.3),
                blurRadius: 20,
                spreadRadius: 5,
              ),
            ],
          ),
          child: CustomPaint(
            painter: _SoundWavePainter(),
          ),
        ),
        if (showText) ...[
          const SizedBox(height: 10),
          ShaderMask(
            shaderCallback: (bounds) => AppColors.logoGradient.createShader(bounds),
            child: Text(
              'EmoTune',
              style: TextStyle(
                fontFamily: 'Georgia',
                fontStyle: FontStyle.italic,
                fontSize: size * 0.28,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _SoundWavePainter extends CustomPainter {
  /// Each eye is a tiny equaliser -- short, tall, short -- so the frequency
  /// reading survives at the 60px home-screen size, where a longer waveform
  /// blurs into a single band.
  static const List<double> _barHalfHeights = [0.055, 0.105, 0.055];
  static const List<double> _eyeCenters = [0.30, 0.70];
  // Wider than the gap between eyes would suggest is needed: the two
  // clusters have to out-group the bars inside them, or six bars read as
  // one row instead of two eyes.
  static const double _barGap = 0.09;

  @override
  void paint(Canvas canvas, Size size) {
    // Stroke scales with the logo: it is rendered anywhere from 60 to 130px,
    // and a fixed width reads chunky at the small end and thin at the large.
    final stroke = size.width * 0.05;

    final barPaint = Paint()
      ..color = Colors.white
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    final eyesY = size.height * 0.40;

    for (final eyeCenter in _eyeCenters) {
      for (var i = 0; i < _barHalfHeights.length; i++) {
        final x = size.width * (eyeCenter + (i - 1) * _barGap);
        final halfHeight = size.height * _barHalfHeights[i];
        canvas.drawLine(
          Offset(x, eyesY - halfHeight),
          Offset(x, eyesY + halfHeight),
          barPaint,
        );
      }
    }

    // Slightly heavier than the bars so the face reads before the waveform.
    final smilePaint = Paint()
      ..color = Colors.white
      ..strokeWidth = stroke * 1.15
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    final smile = Path()
      ..moveTo(size.width * 0.28, size.height * 0.60)
      ..quadraticBezierTo(
        size.width * 0.50,
        size.height * 0.80,
        size.width * 0.72,
        size.height * 0.60,
      );
    canvas.drawPath(smile, smilePaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
