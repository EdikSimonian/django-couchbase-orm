import Foundation
import CouchbaseLiteSwift

/// Manages the local Couchbase Lite database and collections.
class DatabaseManager {
    static let shared = DatabaseManager()

    private(set) var database: Database?
    private(set) var beerCollection: Collection?
    private(set) var breweryCollection: Collection?
    private(set) var ratingCollection: Collection?
    private(set) var blogPageCollection: Collection?
    private(set) var wagtailPageCollection: Collection?

    private let dbName = "brewsync"

    private init() {}

    func initialize() throws {
        // Don't re-initialize if already open
        if database != nil { return }

        database = try Database(name: dbName)
        guard let db = database else { return }

        // Create collections matching Django's collection names
        beerCollection = try db.createCollection(name: "beers_beer", scope: "_default")
        breweryCollection = try db.createCollection(name: "beers_brewery", scope: "_default")
        ratingCollection = try db.createCollection(name: "beers_rating", scope: "_default")
        blogPageCollection = try db.createCollection(name: "home_blogpage", scope: "_default")
        wagtailPageCollection = try db.createCollection(name: "wagtailcore_page", scope: "_default")

        // Create indexes for common queries
        try createIndexes()
    }

    private func createIndexes() throws {
        // Beer indexes
        if let collection = beerCollection {
            let nameIndex = ValueIndexConfiguration(["name"])
            try collection.createIndex(withName: "idx_beer_name", config: nameIndex)

            let styleIndex = ValueIndexConfiguration(["style"])
            try collection.createIndex(withName: "idx_beer_style", config: styleIndex)
        }

        // Rating indexes
        if let collection = ratingCollection {
            let beerIdIndex = ValueIndexConfiguration(["beer_id"])
            try collection.createIndex(withName: "idx_rating_beer", config: beerIdIndex)

            let userIndex = ValueIndexConfiguration(["user_id"])
            try collection.createIndex(withName: "idx_rating_user", config: userIndex)
        }
    }

    // MARK: - Beer CRUD

    func getAllBeers() -> [Beer] {
        guard let collection = beerCollection else { return [] }
        let query = QueryBuilder
            .select(SelectResult.all(), SelectResult.expression(Meta.id))
            .from(DataSource.collection(collection))
            .orderBy(Ordering.property("name").ascending())

        guard let results = try? query.execute() else { return [] }
        return results.compactMap { result in
            guard let dict = result.dictionary(at: 0) else { return nil }
            return beerFromDict(dict, docId: result.string(at: 1) ?? "")
        }
    }

    func getBeer(id: Int) -> Beer? {
        guard let collection = beerCollection else { return nil }
        guard let doc = try? collection.document(id: String(id)) else { return nil }
        return beerFromDocument(doc)
    }

    func saveBeer(_ beer: Beer) throws {
        guard let collection = beerCollection else { return }
        let doc = MutableDocument(id: String(beer.id))
        doc.setInt(beer.id, forKey: "id")
        doc.setString("beer", forKey: "doc_type")
        doc.setString(beer.name, forKey: "name")
        doc.setValue(beer.abv, forKey: "abv")
        doc.setValue(beer.ibu, forKey: "ibu")
        doc.setString(beer.style, forKey: "style")
        doc.setValue(beer.breweryId, forKey: "brewery_id")
        doc.setString(beer.description, forKey: "description")
        doc.setString(beer.imageUrl, forKey: "image_url")
        doc.setDouble(beer.avgRating, forKey: "avg_rating")
        doc.setInt(beer.ratingCount, forKey: "rating_count")
        if let createdAt = beer.createdAt {
            doc.setString(createdAt, forKey: "created_at")
        }
        doc.setString(ISO8601DateFormatter().string(from: Date()), forKey: "updated_at")
        try collection.save(document: doc)
    }

    func deleteBeer(id: Int) throws {
        guard let collection = beerCollection,
              let doc = try? collection.document(id: String(id)) else { return }
        try collection.delete(document: doc)
    }

    // MARK: - Brewery CRUD

    func saveBrewery(_ brewery: Brewery) throws {
        guard let collection = breweryCollection else { return }
        let doc = MutableDocument(id: String(brewery.id))
        doc.setInt(brewery.id, forKey: "id")
        doc.setString("brewery", forKey: "doc_type")
        doc.setString(brewery.name, forKey: "name")
        doc.setString(brewery.city, forKey: "city")
        doc.setString(brewery.state, forKey: "state")
        doc.setString(brewery.country, forKey: "country")
        doc.setString(brewery.description, forKey: "description")
        doc.setString(brewery.website, forKey: "website")
        try collection.save(document: doc)
    }

    func deleteBrewery(id: Int) throws {
        guard let collection = breweryCollection,
              let doc = try? collection.document(id: String(id)) else { return }
        try collection.delete(document: doc)
    }

    func getAllBreweries() -> [Brewery] {
        guard let collection = breweryCollection else { return [] }
        let query = QueryBuilder
            .select(SelectResult.all(), SelectResult.expression(Meta.id))
            .from(DataSource.collection(collection))
            .orderBy(Ordering.property("name").ascending())

        guard let results = try? query.execute() else { return [] }
        return results.compactMap { result in
            guard let dict = result.dictionary(at: 0) else { return nil }
            return breweryFromDict(dict, docId: result.string(at: 1) ?? "")
        }
    }

    func getBrewery(id: Int) -> Brewery? {
        guard let collection = breweryCollection else { return nil }
        guard let doc = try? collection.document(id: String(id)) else { return nil }
        return breweryFromDocument(doc)
    }

    // MARK: - Rating CRUD

    func getRatings(forBeer beerId: Int) -> [Rating] {
        guard let collection = ratingCollection else { return [] }
        let query = QueryBuilder
            .select(SelectResult.all(), SelectResult.expression(Meta.id))
            .from(DataSource.collection(collection))
            .where(Expression.property("beer_id").equalTo(Expression.int(beerId)))

        guard let results = try? query.execute() else { return [] }
        return results.compactMap { result in
            guard let dict = result.dictionary(at: 0) else { return nil }
            return ratingFromDict(dict, docId: result.string(at: 1) ?? "")
        }
    }

    func getUserRating(beerId: Int, userId: Int) -> Rating? {
        let docId = Rating.documentId(beerId: beerId, userId: userId)
        guard let collection = ratingCollection,
              let doc = try? collection.document(id: docId) else { return nil }
        return ratingFromDocument(doc, docId: docId)
    }

    func saveRating(_ rating: Rating) throws {
        guard let collection = ratingCollection else { return }
        let doc = MutableDocument(id: rating.id)
        doc.setString("rating", forKey: "doc_type")
        doc.setInt(rating.beerId, forKey: "beer_id")
        doc.setInt(rating.userId, forKey: "user_id")
        doc.setString(rating.username, forKey: "username")
        doc.setInt(rating.score, forKey: "score")
        doc.setString(rating.createdAt ?? ISO8601DateFormatter().string(from: Date()), forKey: "created_at")
        try collection.save(document: doc)
    }

    // MARK: - Converters

    private func beerFromDocument(_ doc: Document) -> Beer {
        Beer(
            id: Int(doc.id) ?? 0,
            docType: doc.string(forKey: "doc_type") ?? "beer",
            name: doc.string(forKey: "name") ?? "",
            abv: doc.contains(key: "abv") ? doc.double(forKey: "abv") : nil,
            ibu: doc.contains(key: "ibu") ? doc.int(forKey: "ibu") : nil,
            style: doc.string(forKey: "style") ?? "",
            breweryId: doc.contains(key: "brewery_id") ? doc.int(forKey: "brewery_id") : nil,
            description: doc.string(forKey: "description") ?? "",
            imageUrl: doc.string(forKey: "image_url") ?? "",
            avgRating: doc.double(forKey: "avg_rating"),
            ratingCount: doc.int(forKey: "rating_count"),
            createdAt: doc.string(forKey: "created_at"),
            updatedAt: doc.string(forKey: "updated_at")
        )
    }

    private func beerFromDict(_ dict: DictionaryObject, docId: String) -> Beer {
        Beer(
            id: Int(docId) ?? 0,
            docType: dict.string(forKey: "doc_type") ?? "beer",
            name: dict.string(forKey: "name") ?? "",
            abv: dict.contains(key: "abv") ? dict.double(forKey: "abv") : nil,
            ibu: dict.contains(key: "ibu") ? dict.int(forKey: "ibu") : nil,
            style: dict.string(forKey: "style") ?? "",
            breweryId: dict.contains(key: "brewery_id") ? dict.int(forKey: "brewery_id") : nil,
            description: dict.string(forKey: "description") ?? "",
            imageUrl: dict.string(forKey: "image_url") ?? "",
            avgRating: dict.double(forKey: "avg_rating"),
            ratingCount: dict.int(forKey: "rating_count"),
            createdAt: dict.string(forKey: "created_at"),
            updatedAt: dict.string(forKey: "updated_at")
        )
    }

    private func breweryFromDocument(_ doc: Document) -> Brewery {
        Brewery(
            id: Int(doc.id) ?? 0,
            docType: doc.string(forKey: "doc_type") ?? "brewery",
            name: doc.string(forKey: "name") ?? "",
            city: doc.string(forKey: "city") ?? "",
            state: doc.string(forKey: "state") ?? "",
            country: doc.string(forKey: "country") ?? "",
            description: doc.string(forKey: "description") ?? "",
            website: doc.string(forKey: "website") ?? ""
        )
    }

    private func breweryFromDict(_ dict: DictionaryObject, docId: String) -> Brewery {
        Brewery(
            id: Int(docId) ?? 0,
            docType: dict.string(forKey: "doc_type") ?? "brewery",
            name: dict.string(forKey: "name") ?? "",
            city: dict.string(forKey: "city") ?? "",
            state: dict.string(forKey: "state") ?? "",
            country: dict.string(forKey: "country") ?? "",
            description: dict.string(forKey: "description") ?? "",
            website: dict.string(forKey: "website") ?? ""
        )
    }

    private func ratingFromDocument(_ doc: Document, docId: String) -> Rating {
        Rating(
            id: docId,
            docType: doc.string(forKey: "doc_type") ?? "rating",
            beerId: doc.int(forKey: "beer_id"),
            userId: doc.int(forKey: "user_id"),
            username: doc.string(forKey: "username") ?? "",
            score: doc.int(forKey: "score"),
            createdAt: doc.string(forKey: "created_at")
        )
    }

    private func ratingFromDict(_ dict: DictionaryObject, docId: String) -> Rating {
        Rating(
            id: docId,
            docType: dict.string(forKey: "doc_type") ?? "rating",
            beerId: dict.int(forKey: "beer_id"),
            userId: dict.int(forKey: "user_id"),
            username: dict.string(forKey: "username") ?? "",
            score: dict.int(forKey: "score"),
            createdAt: dict.string(forKey: "created_at")
        )
    }

    // MARK: - Cleanup

    // MARK: - Blog

    func getAllBlogPosts() -> [BlogPost] {
        guard let blogCol = blogPageCollection else { return [] }

        let query = QueryBuilder
            .select(SelectResult.all(), SelectResult.expression(Meta.id))
            .from(DataSource.collection(blogCol))

        guard let results = try? query.execute() else { return [] }

        var posts: [BlogPost] = []
        for result in results {
            guard let dict = result.dictionary(at: 0) else { continue }
            let pageId = dict.int(forKey: "page_ptr_id")
            guard pageId > 0 else { continue }

            posts.append(BlogPost(
                id: pageId,
                title: dict.string(forKey: "title") ?? "",
                slug: dict.string(forKey: "slug") ?? "",
                date: dict.string(forKey: "date") ?? "",
                intro: dict.string(forKey: "intro") ?? "",
                body: dict.string(forKey: "body") ?? ""
            ))
        }

        return posts.sorted { $0.date > $1.date }
    }

    func close() {
        try? database?.close()
        database = nil
        beerCollection = nil
        breweryCollection = nil
        ratingCollection = nil
        blogPageCollection = nil
        wagtailPageCollection = nil
    }

    func deleteAndReset() {
        close()
        try? Database.delete(withName: dbName)
        print("[DB] Database deleted for full re-sync")
    }
}
