import Foundation
import OSLog

@MainActor
final class ScheduleSliceCache {
    static let shared = ScheduleSliceCache()

    private let encoder: JSONEncoder
    private let decoder: JSONDecoder
    private let directoryURL: URL
    private let logger = Logger(subsystem: "com.arcadiacoach.app", category: "ScheduleSliceCache")

    private init() {
        let fileManager = FileManager.default
        let baseURL = fileManager.urls(for: .cachesDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
        directoryURL = baseURL.appendingPathComponent("ArcadiaCoachSchedules", isDirectory: true)

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
        self.encoder = encoder

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        self.decoder = decoder
    }

    private func fileURL(for username: String) -> URL {
        let lowered = username.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let safe = lowered.replacingOccurrences(of: "[^a-z0-9_-]", with: "-", options: .regularExpression)
        return directoryURL.appendingPathComponent("\(safe).json", isDirectory: false)
    }

    func store(schedule: CurriculumSchedule, username: String) {
        let url = fileURL(for: username)
        do {
            try FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)
            let data = try encoder.encode(schedule)
            try data.write(to: url, options: .atomic)
        } catch {
            logger.error("Failed to store cached schedule for \(username, privacy: .public): \(error.localizedDescription, privacy: .public)")
        }
    }

    func load(username: String) -> CurriculumSchedule? {
        let url = fileURL(for: username)
        guard FileManager.default.fileExists(atPath: url.path) else {
            return nil
        }
        do {
            let data = try Data(contentsOf: url)
            return try decoder.decode(CurriculumSchedule.self, from: data)
        } catch {
            logger.error("Failed to load cached schedule for \(username, privacy: .public): \(error.localizedDescription, privacy: .public)")
            return nil
        }
    }

    func clear(username: String) {
        let url = fileURL(for: username)
        do {
            if FileManager.default.fileExists(atPath: url.path) {
                try FileManager.default.removeItem(at: url)
            }
        } catch {
            logger.notice("Failed to clear cached schedule for \(username, privacy: .public): \(error.localizedDescription, privacy: .public)")
        }
    }
}
