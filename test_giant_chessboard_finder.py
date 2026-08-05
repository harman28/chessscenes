"""
Offline tests for giant_chessboard_finder.py's pipeline (dedupe, clustering,
existing-venue duplicate flagging). Doesn't touch the network — Overpass/
Nominatim calls aren't exercised here, only the pure data-processing logic.

Run: python3 test_giant_chessboard_finder.py
"""

import unittest

import giant_chessboard_finder as gcf


class TestBuildQueries(unittest.TestCase):
    def test_requires_exactly_one_of_area_or_bbox(self):
        with self.assertRaises(ValueError):
            gcf.build_queries()
        with self.assertRaises(ValueError):
            gcf.build_queries(area="Amsterdam", bbox=(1, 2, 3, 4))

    def test_area_scopes_both_queries(self):
        queries, scope_desc = gcf.build_queries(area="Amsterdam", admin_level="8")
        self.assertIn("Amsterdam", scope_desc)
        for label, q in queries:
            self.assertIn('area["name"="Amsterdam"]["admin_level"="8"]->.searchArea;', q)
            self.assertIn("(area.searchArea)", q)
            self.assertNotIn("(area.searchArea)(area.searchArea)", q)

    def test_bbox_scopes_both_queries(self):
        queries, scope_desc = gcf.build_queries(bbox=(52.28, 4.70, 52.43, 5.02))
        self.assertIn("bbox", scope_desc)
        for label, q in queries:
            self.assertIn("(52.28,4.7,52.43,5.02)", q)
            self.assertNotIn("area[", q)

    def test_rejects_quote_in_area_name(self):
        with self.assertRaises(ValueError):
            gcf.build_queries(area='Amsterdam"; node["sport"="chess"];(')


class TestHaversine(unittest.TestCase):
    def test_zero_distance(self):
        self.assertAlmostEqual(gcf.haversine_m(52.0, 4.0, 52.0, 4.0), 0.0, places=3)

    def test_known_distance(self):
        # Amsterdam Centraal to Amsterdam Zuid, roughly 6km apart
        d = gcf.haversine_m(52.3791, 4.9003, 52.3389, 4.8724)
        self.assertGreater(d, 4000)
        self.assertLess(d, 8000)


class TestMergeAndCluster(unittest.TestCase):
    def test_merge_by_osm_id_combines_matched_by(self):
        candidates = [
            {"osm_type": "node", "osm_id": 1, "lat": 1.0, "lon": 1.0, "tags": {"name": "A"}, "matched_by": {"tagged"}},
            {"osm_type": "node", "osm_id": 1, "lat": 1.0, "lon": 1.0, "tags": {"name": "A"}, "matched_by": {"freetext"}},
        ]
        merged = gcf.merge_by_osm_id(candidates)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["matched_by"], {"tagged", "freetext"})

    def test_spatial_dedupe_merges_nearby_points(self):
        candidates = [
            {"osm_type": "node", "osm_id": 1, "lat": 48.8566, "lon": 2.3522, "tags": {"name": "Board"}, "matched_by": {"tagged"}},
            {"osm_type": "node", "osm_id": 2, "lat": 48.85661, "lon": 2.35222, "tags": {}, "matched_by": {"freetext"}},
        ]
        clustered = gcf.spatial_dedupe(candidates, radius_m=50)
        self.assertEqual(len(clustered), 1)
        self.assertEqual(clustered[0]["cluster_size"], 2)
        self.assertEqual(clustered[0]["tags"]["name"], "Board")

    def test_spatial_dedupe_keeps_far_points_separate(self):
        candidates = [
            {"osm_type": "node", "osm_id": 1, "lat": 48.8566, "lon": 2.3522, "tags": {}, "matched_by": {"tagged"}},
            {"osm_type": "node", "osm_id": 2, "lat": 40.7308, "lon": -73.9973, "tags": {}, "matched_by": {"tagged"}},
        ]
        clustered = gcf.spatial_dedupe(candidates, radius_m=50)
        self.assertEqual(len(clustered), 2)


class TestDuplicateFlagging(unittest.TestCase):
    def test_flags_nearby_existing_venue(self):
        clusters = [
            {"lat": 52.362969, "lon": 4.883705, "osm_type": "node", "osm_id": 1,
             "tags": {}, "matched_by": {"tagged"}, "cluster_osm_refs": ["node/1"], "cluster_size": 1},
        ]
        existing = [{"name": "Max Euweplein", "city": "Amsterdam", "lat": 52.362969674148395, "lng": 4.88370529837886}]
        gcf.flag_possible_duplicates(clusters, existing, radius_m=100)
        self.assertEqual(clusters[0]["possible_duplicate_of"], "Max Euweplein (Amsterdam)")

    def test_no_flag_when_far_from_existing(self):
        clusters = [
            {"lat": 0.0, "lon": 0.0, "osm_type": "node", "osm_id": 1,
             "tags": {}, "matched_by": {"tagged"}, "cluster_osm_refs": ["node/1"], "cluster_size": 1},
        ]
        existing = [{"name": "Max Euweplein", "city": "Amsterdam", "lat": 52.362969674148395, "lng": 4.88370529837886}]
        gcf.flag_possible_duplicates(clusters, existing, radius_m=100)
        self.assertEqual(clusters[0]["possible_duplicate_of"], "")


class TestBuildReviewRows(unittest.TestCase):
    def test_fallback_name_and_csv_schema(self):
        clusters = [
            {"lat": 1.0, "lon": 2.0, "osm_type": "node", "osm_id": 42, "tags": {},
             "matched_by": {"tagged"}, "cluster_osm_refs": ["node/42"], "cluster_size": 1,
             "possible_duplicate_of": "", "duplicate_distance_m": None},
        ]
        rows = gcf.build_review_rows(clusters, geocode=False)
        self.assertEqual(rows[0]["name"], "Unnamed chess feature (node/42)")
        self.assertEqual(rows[0]["labels"], "chess board")
        self.assertEqual(rows[0]["coordinates"], "1.0, 2.0")
        for field in ["name", "labels", "city", "coordinates", "note", "gmap", "link", "image", "days", "id"]:
            self.assertIn(field, rows[0])


if __name__ == "__main__":
    unittest.main()
