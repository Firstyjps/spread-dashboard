import WidgetKit
import SwiftUI

// MARK: - API Response
struct SpreadData: Codable {
    let symbol: String
    let mid_bps: Double?
    let long_bps: Double?
    let short_bps: Double?
}

// MARK: - Timeline Entry
struct SpreadEntry: TimelineEntry {
    let date: Date
    let midBps: Double?
    let longBps: Double?
    let shortBps: Double?
}

// MARK: - Timeline Provider
struct SpreadProvider: TimelineProvider {
    func placeholder(in context: Context) -> SpreadEntry {
        SpreadEntry(date: .now, midBps: 72.5, longBps: 68.3, shortBps: 76.8)
    }

    func getSnapshot(in context: Context, completion: @escaping (SpreadEntry) -> Void) {
        Task {
            let data = await fetchSpread()
            completion(SpreadEntry(
                date: .now,
                midBps: data?.mid_bps,
                longBps: data?.long_bps,
                shortBps: data?.short_bps
            ))
        }
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<SpreadEntry>) -> Void) {
        Task {
            let data = await fetchSpread()
            let entry = SpreadEntry(
                date: .now,
                midBps: data?.mid_bps,
                longBps: data?.long_bps,
                shortBps: data?.short_bps
            )
            // Refresh every 5 minutes
            let next = Calendar.current.date(byAdding: .minute, value: 5, to: .now)!
            completion(Timeline(entries: [entry], policy: .after(next)))
        }
    }

    private func fetchSpread() async -> SpreadData? {
        guard let url = URL(string: "https://dash.firstyjps.com/api/v1/widget/spread") else {
            return nil
        }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            return try JSONDecoder().decode(SpreadData.self, from: data)
        } catch {
            return nil
        }
    }
}

// MARK: - Lock Screen: Inline (single line, like "XAU 72.5 bps")
struct InlineView: View {
    let entry: SpreadEntry

    var body: some View {
        if let bps = entry.midBps {
            Text("XAU \(String(format: "%.1f", bps)) bps")
        } else {
            Text("XAU --")
        }
    }
}

// MARK: - Lock Screen: Circular
struct CircularView: View {
    let entry: SpreadEntry

    var body: some View {
        VStack(spacing: 1) {
            Text("XAU")
                .font(.system(size: 10, weight: .medium))
                .widgetAccentable()
            if let bps = entry.midBps {
                Text(String(format: "%.0f", bps))
                    .font(.system(size: 18, weight: .bold, design: .rounded))
            } else {
                Text("--")
                    .font(.system(size: 18, weight: .bold))
            }
            Text("bps")
                .font(.system(size: 8))
                .foregroundStyle(.secondary)
        }
    }
}

// MARK: - Lock Screen: Rectangular
struct RectangularView: View {
    let entry: SpreadEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("XAU SPREAD")
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(.secondary)
            if let mid = entry.midBps {
                Text("\(String(format: "%.1f", mid)) bps")
                    .font(.system(size: 18, weight: .bold, design: .rounded))
                    .widgetAccentable()
            }
            if let long = entry.longBps, let short = entry.shortBps {
                HStack(spacing: 8) {
                    Label("L \(String(format: "%.1f", long))", systemImage: "arrow.up.right")
                    Label("S \(String(format: "%.1f", short))", systemImage: "arrow.down.right")
                }
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
            }
        }
    }
}

// MARK: - Home Screen: Small
struct SmallWidgetView: View {
    let entry: SpreadEntry

    var bpsColor: Color {
        guard let mid = entry.midBps else { return .gray }
        if mid >= 80 { return .green }
        if mid >= 60 { return .yellow }
        return .red
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("XAU SPREAD")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(.secondary)
                Spacer()
                Circle()
                    .fill(bpsColor)
                    .frame(width: 8, height: 8)
            }

            if let mid = entry.midBps {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(String(format: "%.1f", mid))
                        .font(.system(size: 32, weight: .bold, design: .monospaced))
                        .foregroundStyle(bpsColor)
                    Text("bps")
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                }
            } else {
                Text("--")
                    .font(.system(size: 32, weight: .bold))
                    .foregroundStyle(.secondary)
            }

            if let long = entry.longBps, let short = entry.shortBps {
                HStack {
                    Text("L \(String(format: "%.1f", long))")
                        .foregroundStyle(.blue)
                    Spacer()
                    Text("S \(String(format: "%.1f", short))")
                        .foregroundStyle(.red)
                }
                .font(.system(size: 11, design: .monospaced))
            }

            Spacer()

            Text(entry.date, style: .time)
                .font(.system(size: 9))
                .foregroundStyle(.tertiary)
                .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .padding(12)
        .containerBackground(.black.gradient, for: .widget)
    }
}

// MARK: - Widget Router
struct WidgetEntryView: View {
    @Environment(\.widgetFamily) var family
    let entry: SpreadEntry

    var body: some View {
        switch family {
        case .accessoryInline:
            InlineView(entry: entry)
        case .accessoryCircular:
            CircularView(entry: entry)
        case .accessoryRectangular:
            RectangularView(entry: entry)
        default:
            SmallWidgetView(entry: entry)
        }
    }
}

// MARK: - Widget Definition
@main
struct XAUSpreadWidget: Widget {
    let kind = "XAUSpreadWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: SpreadProvider()) { entry in
            WidgetEntryView(entry: entry)
        }
        .configurationDisplayName("XAU Spread")
        .description("Live XAU spread in BPS")
        .supportedFamilies([
            .accessoryInline,       // Lock Screen: single line
            .accessoryCircular,     // Lock Screen: circle
            .accessoryRectangular,  // Lock Screen: rectangle
            .systemSmall,           // Home Screen: small
        ])
    }
}
