import Foundation

struct Brewery: Identifiable, Codable {
    let id: Int
    var docType: String = "brewery"
    var name: String
    var city: String
    var state: String
    var country: String
    var description: String
    var website: String

    enum CodingKeys: String, CodingKey {
        case id
        case docType = "doc_type"
        case name, city, state, country, description, website
    }
}
