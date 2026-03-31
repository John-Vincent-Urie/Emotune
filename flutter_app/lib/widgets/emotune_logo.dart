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
                color: AppColors.gradientStart.withOpacity(0.3),
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
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    final centerY = size.height * 0.42;
    final startX = size.width * 0.2;
    final endX = size.width * 0.8;
    final totalWidth = endX - startX;
    
    // Draw sound wave bars (eyes)
    final barHeights = [0.12, 0.22, 0.3, 0.22, 0.12, 0.22, 0.3, 0.22, 0.12];
    final barCount = barHeights.length;
    final barWidth = totalWidth / (barCount * 2 - 1);
    
    for (int i = 0; i < barCount; i++) {
      final x = startX + i * barWidth * 2;
      final h = size.height * barHeights[i];
      canvas.drawLine(
        Offset(x, centerY - h),
        Offset(x, centerY + h),
        paint,
      );
    }

    // Smile
    final smilePaint = Paint()
      ..color = Colors.white
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    final smilePath = Path();
    smilePath.moveTo(size.width * 0.3, size.height * 0.65);
    smilePath.quadraticBezierTo(
      size.width * 0.5, size.height * 0.78,
      size.width * 0.7, size.height * 0.65,
    );
    canvas.drawPath(smilePath, smilePaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
