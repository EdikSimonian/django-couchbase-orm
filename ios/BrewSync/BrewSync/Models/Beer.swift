import Foundation

struct Beer: Identifiable, Codable {
    let id: Int
    var docType: String = "beer"
    var name: String
    var abv: Double?
    var ibu: Int?
    var style: String
    var breweryId: Int?
    var description: String
    var imageUrl: String
    var avgRating: Double
    var ratingCount: Int
    var createdAt: String?
    var updatedAt: String?

    // Transient — populated from brewery lookup
    var breweryName: String?

    enum CodingKeys: String, CodingKey {
        case id
        case docType = "doc_type"
        case name, abv, ibu, style
        case breweryId = "brewery_id"
        case description
        case imageUrl = "image_url"
        case avgRating = "avg_rating"
        case ratingCount = "rating_count"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    static let styleChoices = [
        "IPA", "Pale Ale", "Stout", "Porter", "Lager", "Pilsner",
        "Wheat", "Sour", "Amber", "Brown Ale", "Belgian", "Saison",
        "Hazy IPA", "Double IPA", "Other"
    ]
}
