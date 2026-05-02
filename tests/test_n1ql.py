"""Tests for the N1QL query builder."""


from django_couchbase_orm.query.n1ql import N1QLQuery


class TestN1QLBasic:
    def test_keyspace(self):
        q = N1QLQuery("mybucket", "myscope", "mycoll")
        assert q.keyspace == "`mybucket`.`myscope`.`mycoll`"

    def test_select_all(self):
        q = N1QLQuery("b", "s", "c")
        stmt, params = q.build()
        assert stmt == "SELECT d.* FROM `b`.`s`.`c` AS d"
        assert params == []

    def test_select_with_meta_id(self):
        q = N1QLQuery("b", "s", "c")
        q.include_meta_id()
        stmt, params = q.build()
        assert "META(d).id AS __id" in stmt
        assert "d.*" in stmt

    def test_select_specific_fields(self):
        q = N1QLQuery("b", "s", "c")
        q.select("name", "age")
        stmt, params = q.build()
        assert "d.`name`" in stmt
        assert "d.`age`" in stmt
        assert "d.*" not in stmt

    def test_select_count(self):
        q = N1QLQuery("b", "s", "c")
        q.select_count()
        stmt, params = q.build()
        assert "COUNT(*) AS `__count`" in stmt

    def test_where(self):
        q = N1QLQuery("b", "s", "c")
        p = q.add_param("active")
        q.where(f"d.`status` = {p}")
        stmt, params = q.build()
        assert "WHERE (d.`status` = $1)" in stmt
        assert params == ["active"]

    def test_where_multiple(self):
        q = N1QLQuery("b", "s", "c")
        p1 = q.add_param("active")
        q.where(f"d.`status` = {p1}")
        p2 = q.add_param(18)
        q.where(f"d.`age` >= {p2}")
        stmt, params = q.build()
        assert "WHERE (d.`status` = $1) AND (d.`age` >= $2)" in stmt
        assert params == ["active", 18]

    def test_order_by_asc(self):
        q = N1QLQuery("b", "s", "c")
        q.order_by("name")
        stmt, _ = q.build()
        assert "ORDER BY d.`name` ASC" in stmt

    def test_order_by_desc(self):
        q = N1QLQuery("b", "s", "c")
        q.order_by("-name")
        stmt, _ = q.build()
        assert "ORDER BY d.`name` DESC" in stmt

    def test_order_by_multiple(self):
        q = N1QLQuery("b", "s", "c")
        q.order_by("-age", "name")
        stmt, _ = q.build()
        assert "ORDER BY d.`age` DESC, d.`name` ASC" in stmt

    def test_limit(self):
        q = N1QLQuery("b", "s", "c")
        q.limit(10)
        stmt, params = q.build()
        assert "LIMIT $1" in stmt
        assert 10 in params

    def test_offset(self):
        q = N1QLQuery("b", "s", "c")
        q.offset(20)
        stmt, params = q.build()
        assert "OFFSET $1" in stmt
        assert 20 in params

    def test_limit_and_offset(self):
        q = N1QLQuery("b", "s", "c")
        q.limit(10).offset(20)
        stmt, params = q.build()
        assert "LIMIT $1" in stmt
        assert "OFFSET $2" in stmt
        assert params == [10, 20]

    def test_use_keys_single(self):
        q = N1QLQuery("b", "s", "c")
        q.use_keys(["key1"])
        stmt, params = q.build()
        assert "USE KEYS $1" in stmt
        assert params == ["key1"]

    def test_use_keys_multiple(self):
        q = N1QLQuery("b", "s", "c")
        q.use_keys(["key1", "key2"])
        stmt, params = q.build()
        assert "USE KEYS $1" in stmt
        assert params == [["key1", "key2"]]

    def test_full_query(self):
        q = N1QLQuery("beer-sample", "_default", "_default")
        q.include_meta_id()
        p1 = q.add_param("brewery")
        q.where(f"d.`type` = {p1}")
        p2 = q.add_param("United States")
        q.where(f"d.`country` = {p2}")
        q.order_by("name")
        q.limit(10)
        q.offset(0)

        stmt, params = q.build()
        assert "META(d).id AS __id" in stmt
        # CAS is now hydrated alongside the id so optimistic locking works on
        # queryset-loaded documents.
        assert "META(d).cas AS __cas" in stmt
        assert "d.*" in stmt
        assert "FROM `beer-sample`.`_default`.`_default` AS d" in stmt
        assert "WHERE" in stmt
        assert "d.`type` = $1" in stmt
        assert "d.`country` = $2" in stmt
        assert "ORDER BY d.`name` ASC" in stmt
        assert "LIMIT $3" in stmt
        assert "OFFSET $4" in stmt
        assert params == ["brewery", "United States", 10, 0]


class TestN1QLClone:
    def test_clone_is_independent(self):
        q1 = N1QLQuery("b", "s", "c")
        q1.where("d.`x` = 1")
        q1.order_by("name")
        q1.limit(10)

        q2 = q1.clone()
        q2.where("d.`y` = 2")
        q2.limit(20)

        stmt1, _ = q1.build()
        stmt2, _ = q2.build()
        assert "y" not in stmt1
        assert "y" in stmt2


class TestN1QLUpdate:
    def test_build_update(self):
        q = N1QLQuery("b", "s", "c")
        p = q.add_param("brewery")
        q.where(f"d.`type` = {p}")

        stmt, params = q.build_update({"name": "New Name", "city": "SF"})
        assert stmt.startswith("UPDATE `b`.`s`.`c` AS d SET")
        assert "d.`name` = $2" in stmt
        assert "d.`city` = $3" in stmt
        assert "WHERE (d.`type` = $1)" in stmt
        assert params == ["brewery", "New Name", "SF"]


class TestN1QLDelete:
    def test_build_delete(self):
        q = N1QLQuery("b", "s", "c")
        p = q.add_param("inactive")
        q.where(f"d.`status` = {p}")

        stmt, params = q.build_delete()
        assert stmt.startswith("DELETE FROM `b`.`s`.`c` AS d")
        assert "WHERE (d.`status` = $1)" in stmt
        assert params == ["inactive"]

    def test_build_delete_no_where(self):
        q = N1QLQuery("b", "s", "c")
        stmt, params = q.build_delete()
        assert "WHERE" not in stmt
        assert params == []
