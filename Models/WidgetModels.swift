import Foundation

enum WidgetType: String, Codable { case Card, List, StatRow, MiniChatbot, ArcadiaChatbot }

struct WidgetCardSection: Codable, Hashable {
    var heading: String?
    var items: [String]
}

struct WidgetCardProps: Codable, Hashable {
    var title: String
    var sections: [WidgetCardSection]?
}

struct WidgetListRow: Codable, Hashable {
    var label: String
    var href: String?
    var meta: String?
}

struct WidgetListProps: Codable, Hashable {
    var title: String?
    var rows: [WidgetListRow]
}

struct WidgetStatItem: Codable, Hashable {
    var label: String
    var value: String
}

struct WidgetStatRowProps: Codable, Hashable {
    var items: [WidgetStatItem]

    /// Optional override for how many items should appear per row when rendered in SwiftUI.
    /// When omitted, the view adapts based on its layout heuristics.
    var itemsPerRow: Int?

    init(items: [WidgetStatItem], itemsPerRow: Int? = nil) {
        self.items = items
        self.itemsPerRow = itemsPerRow
    }
}

struct ArcadiaChatbotLevelOption: Codable, Hashable {
    var value: String
    var label: String
}

struct ArcadiaChatbotMessage: Codable, Hashable {
    var id: String
    var role: String
    var text: String
}

struct ArcadiaChatbotProps: Codable, Hashable {
    var title: String
    var webEnabled: Bool
    var showTonePicker: Bool
    var level: String
    var levelLabel: String
    var levels: [ArcadiaChatbotLevelOption]
    var messages: [ArcadiaChatbotMessage]
    var placeholder: String?
    var status: String?

    init(
        title: String,
        webEnabled: Bool,
        showTonePicker: Bool,
        level: String,
        levelLabel: String,
        levels: [ArcadiaChatbotLevelOption],
        messages: [ArcadiaChatbotMessage],
        placeholder: String? = nil,
        status: String? = nil
    ) {
        self.title = title
        self.webEnabled = webEnabled
        self.showTonePicker = showTonePicker
        self.level = level
        self.levelLabel = levelLabel
        self.levels = levels
        self.messages = messages
        self.placeholder = placeholder
        self.status = status
    }

    init(legacy: LegacyMiniChatbotProps) {
        self.init(
            title: legacy.title,
            webEnabled: false,
            showTonePicker: false,
            level: "medium",
            levelLabel: "Medium",
            levels: ArcadiaChatbotProps.defaultLevels,
            messages: legacy.messages.map { ArcadiaChatbotMessage(id: $0.id, role: $0.role, text: $0.text) },
            placeholder: legacy.placeholder,
            status: legacy.status.isEmpty ? nil : legacy.status
        )
    }

    static var defaultLevels: [ArcadiaChatbotLevelOption] {
        [
            ArcadiaChatbotLevelOption(value: "minimal", label: "Minimal"),
            ArcadiaChatbotLevelOption(value: "low", label: "Low"),
            ArcadiaChatbotLevelOption(value: "medium", label: "Medium"),
            ArcadiaChatbotLevelOption(value: "high", label: "High"),
        ]
    }

    func legacyProps() -> LegacyMiniChatbotProps {
        LegacyMiniChatbotProps(
            title: title,
            status: status ?? "",
            placeholder: placeholder ?? "What should we explore?",
            messages: messages.map { LegacyMiniChatbotMessage(id: $0.id, role: $0.role, text: $0.text) }
        )
    }
}

struct LegacyMiniChatbotMessage: Codable, Hashable {
    var id: String
    var role: String
    var text: String
}

struct LegacyMiniChatbotProps: Codable, Hashable {
    var title: String
    var status: String
    var placeholder: String
    var messages: [LegacyMiniChatbotMessage]
}

struct Widget: Codable, Hashable {
    var type: WidgetType
    var propsCard: WidgetCardProps?
    var propsList: WidgetListProps?
    var propsStat: WidgetStatRowProps?
    var propsArcadiaChatbot: ArcadiaChatbotProps?
    private var legacyMiniChatbot: LegacyMiniChatbotProps?

    enum CodingKeys: String, CodingKey { case type, props }

    // Decode generic {type, props:{...}} into typed props
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try c.decode(WidgetType.self, forKey: .type)
        // Generic props dictionary
        let raw = try c.decode([String:AnyCodable].self, forKey: .props)
        let data = try JSONSerialization.data(withJSONObject: raw.mapValues(\.value))
        switch type {
        case .Card: propsCard = try JSONDecoder().decode(WidgetCardProps.self, from: data)
        case .List: propsList = try JSONDecoder().decode(WidgetListProps.self, from: data)
        case .StatRow: propsStat = try JSONDecoder().decode(WidgetStatRowProps.self, from: data)
        case .ArcadiaChatbot:
            propsArcadiaChatbot = try JSONDecoder().decode(ArcadiaChatbotProps.self, from: data)
        case .MiniChatbot:
            legacyMiniChatbot = try JSONDecoder().decode(LegacyMiniChatbotProps.self, from: data)
            propsArcadiaChatbot = legacyMiniChatbot.map(ArcadiaChatbotProps.init(legacy:))
        }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(type, forKey: .type)
        let props: Any
        switch type {
        case .Card: props = propsCard ?? WidgetCardProps(title: "", sections: nil)
        case .List: props = propsList ?? WidgetListProps(title: nil, rows: [])
        case .StatRow: props = propsStat ?? WidgetStatRowProps(items: [])
        case .ArcadiaChatbot:
            props = propsArcadiaChatbot ?? ArcadiaChatbotProps(
                title: "Arcadia Coach",
                webEnabled: false,
                showTonePicker: false,
                level: "medium",
                levelLabel: "Medium",
                levels: ArcadiaChatbotProps.defaultLevels,
                messages: []
            )
        case .MiniChatbot:
            let legacy = legacyMiniChatbot ?? propsArcadiaChatbot?.legacyProps() ?? LegacyMiniChatbotProps(
                title: "Arcadia Coach",
                status: "",
                placeholder: "What should we explore?",
                messages: []
            )
            props = legacy
        }
        let propsData = try JSONEncoder().encode(AnyCodableEncodable(props))
        let propsObj = try JSONSerialization.jsonObject(with: propsData)
        try c.encode(AnyCodable(propsObj), forKey: .props)
    }
}

// AnyCodable helpers
struct AnyCodable: Codable {
    let value: Any
    init(_ value: Any) { self.value = value }
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if let v = try? c.decode(String.self) { value = v; return }
        if let v = try? c.decode(Double.self) { value = v; return }
        if let v = try? c.decode(Bool.self) { value = v; return }
        if let v = try? c.decode([AnyCodable].self) { value = v.map(\.value); return }
        if let v = try? c.decode([String:AnyCodable].self) { value = v.mapValues(\.value); return }
        value = NSNull()
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch value {
        case let v as String: try c.encode(v)
        case let v as Double: try c.encode(v)
        case let v as Int: try c.encode(Double(v))
        case let v as Bool: try c.encode(v)
        case let v as [Any]:
            try c.encode(v.map(AnyCodable.init))
        case let v as [String:Any]:
            try c.encode(v.mapValues(AnyCodable.init))
        default: try c.encodeNil()
        }
    }
}

struct AnyCodableEncodable: Encodable {
    let value: Any
    init(_ value: Any) { self.value = value }
    func encode(to encoder: Encoder) throws { try AnyCodable(value).encode(to: encoder) }
}

struct WidgetEnvelope: Codable {
    var display: String?
    var widgets: [Widget]
    var citations: [String]?
}
