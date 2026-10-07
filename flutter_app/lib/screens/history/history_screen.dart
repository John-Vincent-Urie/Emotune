import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/emotion_chip.dart';
import 'package:intl/intl.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key, this.isActive = false});

  /// MainShell keeps every tab alive inside an IndexedStack, so this screen is
  /// only built once. Without a signal for "the tab is now on screen" the list
  /// would keep showing whatever was on the server when the app launched.
  final bool isActive;

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabCtrl;
  List<dynamic> _history = [];
  List<dynamic> _stats = [];
  bool _loading = false;
  bool _loadInFlight = false;
  bool _hasLoaded = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 2, vsync: this);
    if (widget.isActive) {
      _load();
    }
  }

  @override
  void didUpdateWidget(covariant HistoryScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Refetch every time the tab comes forward: a prompt submitted on Home has
    // already written new rows by the time the user gets here.
    if (widget.isActive && !oldWidget.isActive) {
      _load();
    }
  }

  @override
  void dispose() {
    _tabCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (_loadInFlight) return;
    _loadInFlight = true;

    // Only blank the screen out on the very first fetch. Later refreshes keep
    // the existing rows visible so switching tabs doesn't flash a spinner.
    if (!_hasLoaded) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }

    try {
      final results = await Future.wait([
        ApiService.getHistory(),
        ApiService.getEmotionStats(),
      ]);
      if (!mounted) return;
      setState(() {
        _history = results[0];
        _stats = results[1];
        _loading = false;
        _hasLoaded = true;
        _error = null;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.message;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Could not load your history right now.';
      });
    } finally {
      _loadInFlight = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        title: const Text('History'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _load,
          ),
        ],
        bottom: TabBar(
          controller: _tabCtrl,
          indicatorColor: context.emoColors.accentText,
          labelColor: context.emoColors.accentText,
          unselectedLabelColor: isDark ? Colors.white54 : Colors.black54,
          tabs: const [
            Tab(text: 'Prompts'),
            Tab(text: 'Emotion Stats'),
          ],
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : TabBarView(
              controller: _tabCtrl,
              children: [
                RefreshIndicator(
                  onRefresh: _load,
                  child: _buildHistoryList(isDark),
                ),
                RefreshIndicator(
                  onRefresh: _load,
                  child: _buildPieChart(isDark),
                ),
              ],
            ),
    );
  }

  /// Placeholders have to stay scrollable or pull-to-refresh can't be started
  /// from an empty tab.
  Widget _buildPlaceholder(bool isDark, String message, {bool isError = false}) {
    return LayoutBuilder(
      builder: (ctx, constraints) => ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 32),
                    child: Text(
                      message,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                          color: isDark ? Colors.white54 : Colors.black54),
                    ),
                  ),
                  if (isError) ...[
                    const SizedBox(height: 12),
                    TextButton(
                      onPressed: _load,
                      child: const Text('Try again'),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHistoryList(bool isDark) {
    if (_error != null && _history.isEmpty) {
      return _buildPlaceholder(isDark, _error!, isError: true);
    }
    if (_history.isEmpty) {
      return _buildPlaceholder(isDark, 'No history yet');
    }

    return ListView.builder(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(16),
      itemCount: _history.length,
      itemBuilder: (ctx, i) {
        final item = _history[i];
        final emotion = item['detected_emotion'] ?? 'mixed';
        final color = AppColors.emotionColors[emotion] ?? AppColors.accent;
        final date = DateTime.tryParse(item['created_at'] ?? '');

        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: isDark ? AppColors.darkCard : Colors.white,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: color.withValues(alpha: 0.3)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: color.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: color),
                    ),
                    // The mood color stays on the tint and border; as text
                    // several moods fell under 3:1 in one theme or the other.
                    child: Text(
                      emotion.toUpperCase(),
                      style: TextStyle(
                          color: context.emoColors.textPrimary,
                          fontSize: 11,
                          fontWeight: FontWeight.bold),
                    ),
                  ),
                  const Spacer(),
                  if (date != null)
                    Text(
                      DateFormat('MMM d, h:mm a').format(date.toLocal()),
                      style: TextStyle(
                          color: context.emoColors.textSecondary,
                          fontSize: 11),
                    ),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                item['prompt_text'] ?? '',
                style: TextStyle(
                    color: isDark ? Colors.white70 : Colors.black87,
                    fontSize: 14),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.05),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  item['ai_response'] ?? '',
                  style: TextStyle(
                      color: isDark ? Colors.white70 : Colors.black54,
                      fontSize: 12,
                      fontStyle: FontStyle.italic),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildPieChart(bool isDark) {
    if (_error != null && _stats.isEmpty) {
      return _buildPlaceholder(isDark, _error!, isError: true);
    }
    if (_stats.isEmpty) {
      return _buildPlaceholder(isDark, 'No emotion data yet');
    }

    final total = _stats.fold<int>(0, (sum, s) => sum + (s['count'] as int));
    if (total == 0) {
      return _buildPlaceholder(isDark, 'No emotion data yet');
    }

    final sections = _stats.map<PieChartSectionData>((s) {
      final emotion = s['detected_emotion'] as String;
      final count = s['count'] as int;
      final pct = count / total * 100;
      final color = AppColors.emotionColors[emotion] ?? AppColors.accent;

      return PieChartSectionData(
        color: color,
        value: pct,
        title: '${pct.toStringAsFixed(0)}%',
        radius: 80,
        // White on the yellow and tan slices was under 2:1.
        titleStyle: TextStyle(
            color: EmotionChip.inkFor(color),
            fontSize: 11,
            fontWeight: FontWeight.bold),
      );
    }).toList();

    return SingleChildScrollView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(24),
      child: Column(
        children: [
          const Text('Your Emotion Distribution',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 24),
          SizedBox(
            height: 240,
            child: PieChart(
              PieChartData(
                sections: sections,
                centerSpaceRadius: 40,
                sectionsSpace: 2,
              ),
            ),
          ),
          const SizedBox(height: 24),
          // Legend
          Wrap(
            spacing: 12,
            runSpacing: 10,
            children: _stats.map<Widget>((s) {
              final emotion = s['detected_emotion'] as String;
              final count = s['count'] as int;
              final color =
                  AppColors.emotionColors[emotion] ?? AppColors.accent;
              return Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                      width: 12,
                      height: 12,
                      decoration: BoxDecoration(
                          color: color, shape: BoxShape.circle)),
                  const SizedBox(width: 6),
                  Text(
                    '${emotion[0].toUpperCase()}${emotion.substring(1)} ($count)',
                    style: TextStyle(
                        color: isDark ? Colors.white70 : Colors.black54,
                        fontSize: 13),
                  ),
                ],
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}
