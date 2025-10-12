import Foundation

struct GameState: Codable {
    var elo: [String:Int] = [:]
    var xp: Int = 0
    var level: Int = 1
    var streak: Int = 0

    static func xpGain(from delta: [String:Int]) -> Int {
        max(1, delta.values.filter{$0 > 0}.reduce(0,+)) // only positive deltas
    }
    static func levelFromXP(_ xp: Int) -> Int { max(1, Int(sqrt(Double(xp))/2.0) + 1) }
}
