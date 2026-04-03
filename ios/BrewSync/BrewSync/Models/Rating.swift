import Foundation

struct Rating: Identifiable, Codable {
    var id: String  // "rating::{beer_id}::{user_id}"
    var docType: String = "rating"
    var beerId: Int
    var userId: Int
    var username: String
    var score: Int
    var createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case docType = "doc_type"
        case beerId = "beer_id"
        case userId = "user_id"
        case username, score
        case createdAt = "created_at"
    }

    static func documentId(beerId: Int, userId: Int) -> String {
        "rating::\(beerId)::\(userId)"
    }
}
