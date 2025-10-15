import SwiftUI

struct CitationFootnotesView: View {
    let groups: [CitationFormatter.Group]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Sources")
                .font(.caption.bold())
                .foregroundStyle(.secondary)
            ForEach(groups) { group in
                VStack(alignment: .leading, spacing: 4) {
                    Text("[\(group.marker)]")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.primary)
                    ForEach(group.targets) { target in
                        HStack(alignment: .center, spacing: 6) {
                            Image(systemName: target.systemImageName)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(target.displayLabel)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(nil)
                        }
                    }
                }
                .padding(10)
                .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
            }
        }
        .selectableContent()
    }
}
