import Foundation

struct GameState: Codable {
    var elo: [String:Int] = [
        "Python":1100,"NumPy":1100,"PyTorch":1100,"Tokenization":1100,"RAG":1100,"Eval":1100,"LLM-Ops":1100
    ]
    var xp: Int = 0
    var level: Int = 1
    var streak: Int = 0

    static func xpGain(from delta: [String:Int]) -> Int {
        max(1, delta.values.filter{$0 > 0}.reduce(0,+)) // only positive deltas
    }
    static func levelFromXP(_ xp: Int) -> Int { max(1, Int(sqrt(Double(xp))/2.0) + 1) }
}
