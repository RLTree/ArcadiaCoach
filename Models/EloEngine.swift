import Foundation

struct EloEngine {
    static func expected(_ R: Double, _ Rp: Double) -> Double {
        1.0 / (1.0 + pow(10.0, (Rp - R)/400.0))
    }
    static func update(elo: [String:Int], skillWeights: [String:Double], score: Double, problemRating: Int, K: Int) -> (updated: [String:Int], delta: [String:Int]) {
        var e = elo; var d: [String:Int] = [:]
        let sum = skillWeights.values.reduce(0,+)
        for (skill, w0) in skillWeights {
            let w = sum > 0 ? max(0.0, w0)/sum : 0.0
            let R = Double(e[skill] ?? 1100)
            let E = expected(R, Double(problemRating))
            let newR = Int((R + Double(K) * w * (score - E)).rounded())
            d[skill] = newR - (e[skill] ?? 1100)
            e[skill] = newR
        }
        return (e,d)
    }
}
