import Foundation

struct ChatAttachment: Identifiable, Codable, Hashable {
    var id: String
    var name: String
    var mimeType: String
    var size: Int
    var preview: String?
    var openAIFileId: String?
    var addedAt: Date

    init(
        id: String,
        name: String,
        mimeType: String,
        size: Int,
        preview: String?,
        openAIFileId: String?,
        addedAt: Date = Date()
    ) {
        self.id = id
        self.name = name
        self.mimeType = mimeType
        self.size = size
        self.preview = preview
        self.openAIFileId = openAIFileId
        self.addedAt = addedAt
    }

    var sizeLabel: String {
        let formatter = ByteCountFormatter()
        formatter.allowedUnits = [.useKB, .useMB]
        formatter.countStyle = .file
        return formatter.string(fromByteCount: Int64(size))
    }

    var previewSnippet: String? {
        guard let preview else { return nil }
        let trimmed = preview.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        return String(trimmed.prefix(220))
    }

    var iconSystemName: String {
        if mimeType.contains("image/") { return "photo" }
        if mimeType.contains("pdf") { return "doc.richtext" }
        if mimeType.contains("zip") { return "archivebox" }
        if mimeType.contains("text") { return "doc.text" }
        if mimeType.contains("audio") { return "waveform" }
        if mimeType.contains("video") { return "film" }
        return "paperclip"
    }
}

