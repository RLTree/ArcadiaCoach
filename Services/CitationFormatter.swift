import Foundation

enum CitationFormatter {
    struct Target: Identifiable, Hashable {
        enum Kind {
            case file
            case search
            case url
            case tool
            case unknown
        }

        let raw: String
        let kind: Kind

        var id: String { raw }

        var displayLabel: String {
            switch kind {
            case .file:
                if let number = numericSuffix(from: raw) {
                    return "Attachment \(number)"
                }
                return "Attachment"
            case .search:
                if let number = numericSuffix(from: raw) {
                    return "Web result \(number)"
                }
                return "Web result"
            case .url:
                return raw
            case .tool:
                if let number = numericSuffix(from: raw) {
                    return "Tool output \(number)"
                }
                return "Tool output"
            case .unknown:
                return raw
            }
        }

        var systemImageName: String {
            switch kind {
            case .file:
                return "doc.text"
            case .search:
                return "magnifyingglass"
            case .url:
                return "link"
            case .tool:
                return "wrench"
            case .unknown:
                return "questionmark.circle"
            }
        }
    }

    struct Group: Identifiable, Hashable {
        let marker: Int
        let targets: [Target]

        var id: Int { marker }
    }

    struct ParseResult {
        let displayText: String
        let groups: [Group]
        let nextMarker: Int
    }

    private static let startToken: Character = ""
    private static let endToken: Character = ""
    private static let separator: Character = ""

    static func parse(_ raw: String, startingAt marker: Int = 1) -> ParseResult {
        guard raw.contains(startToken) else {
            return ParseResult(displayText: raw, groups: [], nextMarker: marker)
        }

        var sanitized = ""
        var groups: [Group] = []
        var currentMarker = marker

        var index = raw.startIndex
        while index < raw.endIndex {
            let character = raw[index]
            if character == startToken {
                guard let closing = raw[index...].firstIndex(of: endToken) else {
                    sanitized.append(character)
                    index = raw.index(after: index)
                    continue
                }
                let payloadStart = raw.index(after: index)
                let payload = String(raw[payloadStart..<closing])
                let outcome = parsePayload(payload, marker: currentMarker)
                sanitized.append(outcome.replacement)
                if let group = outcome.group {
                    groups.append(group)
                    currentMarker += 1
                }
                index = raw.index(after: closing)
            } else {
                sanitized.append(character)
                index = raw.index(after: index)
            }
        }

        return ParseResult(displayText: sanitized, groups: groups, nextMarker: currentMarker)
    }

    private static func parsePayload(_ payload: String, marker: Int) -> (replacement: String, group: Group?) {
        let parts = payload.split(separator: separator)
        guard let directive = parts.first else {
            return ("", nil)
        }
        if directive == "cite" {
            let targets = parts.dropFirst().map { Target(raw: String($0), kind: classifyTarget(String($0))) }.filter { !$0.raw.isEmpty }
            guard !targets.isEmpty else {
                return ("", nil)
            }
            return ("[\(marker)]", Group(marker: marker, targets: targets))
        }
        if directive == "url" {
            let urlTargets = parts.dropFirst().map { Target(raw: String($0), kind: .url) }
            guard !urlTargets.isEmpty else {
                return ("", nil)
            }
            return ("[\(marker)]", Group(marker: marker, targets: urlTargets))
        }
        return ("", nil)
    }

    private static func classifyTarget(_ value: String) -> Target.Kind {
        if value.hasPrefix("http://") || value.hasPrefix("https://") {
            return .url
        }
        if value.contains("file") {
            return .file
        }
        if value.contains("search") {
            return .search
        }
        if value.contains("tool") {
            return .tool
        }
        return .unknown
    }

    private static func numericSuffix(from value: String) -> String? {
        let digits = value.reversed().prefix { $0.isNumber }
        guard !digits.isEmpty else { return nil }
        return String(digits.reversed())
    }
}
