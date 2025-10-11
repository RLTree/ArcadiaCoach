import XCTest
@testable import ArcadiaCoach

final class BackendServiceTests: XCTestCase {
    func testEndpointBuildsAPIPath() {
        let url = BackendService.endpoint(baseURL: "https://example.com", path: "api/session/lesson")
        XCTAssertEqual(url?.absoluteString, "https://example.com/api/session/lesson")
    }

    func testEndpointHandlesTrailingSlash() {
        let url = BackendService.endpoint(baseURL: "https://example.com/", path: "api/session/chat")
        XCTAssertEqual(url?.absoluteString, "https://example.com/api/session/chat")
    }

    func testLoadLessonThrowsWhenBackendMissing() async {
        do {
            _ = try await BackendService.loadLesson(baseURL: " ", sessionId: nil, topic: "swift")
            XCTFail("Expected missingBackend error")
        } catch let error as BackendServiceError {
            XCTAssertEqual(error, .missingBackend)
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }
}
