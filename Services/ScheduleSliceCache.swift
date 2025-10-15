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

    private func safeUsername(_ username: String) -> String {
        let lowered = username.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return lowered.replacingOccurrences(of: "[^a-z0-9_-]", with: "-", options: .regularExpression)
    }

    private func fileURL(for username: String, startDay: Int) -> URL {
        let safe = safeUsername(username)
        let filename = startDay == 0 ? "\(safe).json" : "\(safe)-\(startDay).json"
        return directoryURL.appendingPathComponent(filename, isDirectory: false)
    }

    func store(schedule: CurriculumSchedule, username: String, startDay: Int? = nil) {
        let start = startDay ?? schedule.slice?.startDay ?? 0
        let url = fileURL(for: username, startDay: start)
        do {
            try FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)
            let data = try encoder.encode(schedule)
            try data.write(to: url, options: .atomic)
        } catch {
            logger.error("Failed to store cached schedule for \(username, privacy: .public): \(error.localizedDescription, privacy: .public)")
        }
    }

    func load(username: String, startDay: Int? = nil) -> CurriculumSchedule? {
        let start = startDay ?? 0
        let url = fileURL(for: username, startDay: start)
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
        do {
            if FileManager.default.fileExists(atPath: directoryURL.path) {
                let contents = try FileManager.default.contentsOfDirectory(at: directoryURL, includingPropertiesForKeys: nil, options: .skipsHiddenFiles)
                let prefix = safeUsername(username)
                for file in contents where file.lastPathComponent.hasPrefix(prefix) {
                    try? FileManager.default.removeItem(at: file)
                }
            }
        } catch {
            logger.notice("Failed to clear cached schedule for \(username, privacy: .public): \(error.localizedDescription, privacy: .public)")
        }
    }
}
