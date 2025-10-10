import XCTest
@testable import ArcadiaCoach

final class EloEngineTests: XCTestCase {
    func testEloUpdate() {
        let elo = ["Python":1100]
        let (u, d) = EloEngine.update(elo: elo, skillWeights: ["Python":1.0], score: 1.0, problemRating: 1200, K: 24)
        XCTAssertNotNil(u["Python"])
        XCTAssertNotEqual(u["Python"], 1100)
        XCTAssertTrue((d["Python"] ?? 0) != 0)
    }
}
