import Foundation
import OSLog

enum ChatKitResource {
    private static let logger = Logger(subsystem: "com.arcadiacoach.app", category: "ChatKitResource")

    struct InlineDiagnostics: Equatable {
        let byteCount: Int
        let isFallbackStub: Bool
    }

    static func inlineModuleBase64() -> String {
        guard let result = loadInlineModule() else {
            return ""
        }
        let base64 = result.data.base64EncodedString()
        if result.diagnostics.isFallbackStub {
            logger.notice("ChatKit inline fallback stub is bundled (\(result.diagnostics.byteCount, privacy: .public) bytes). Replace with official ChatKit build for production.")
        } else {
            logger.debug("Loaded ChatKit inline module (\(result.diagnostics.byteCount, privacy: .public) bytes).")
        }
        return base64
    }

    static func inlineModuleDiagnostics() -> InlineDiagnostics? {
        guard let result = loadInlineModule() else {
            return nil
        }
        return result.diagnostics
    }

    private static func loadInlineModule() -> (data: Data, diagnostics: InlineDiagnostics)? {
        guard let url = Bundle.main.url(
            forResource: "chatkit.inline",
            withExtension: "mjs",
            subdirectory: "Resources/ChatKit"
        ) ?? Bundle.main.url(forResource: "chatkit.inline", withExtension: "mjs") else {
            logger.debug("ChatKit inline module not found in bundle.")
            return nil
        }
        do {
            let data = try Data(contentsOf: url)
            let stubSignature = "Local inline ChatKit fallback is active."
            let isStub = data.contains(stubSignature.data(using: .utf8) ?? Data())
            let diagnostics = InlineDiagnostics(
                byteCount: data.count,
                isFallbackStub: isStub
            )
            return (data, diagnostics)
        } catch {
            logger.error("Failed to load ChatKit inline module: \(error.localizedDescription, privacy: .public)")
            return nil
        }
    }

}
