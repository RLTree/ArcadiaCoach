import Foundation

enum WidgetType: String, Codable { case Card, List, StatRow }

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
}

struct Widget: Codable, Hashable {
    var type: WidgetType
    var propsCard: WidgetCardProps?
    var propsList: WidgetListProps?
    var propsStat: WidgetStatRowProps?

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
