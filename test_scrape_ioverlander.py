#!/usr/bin/env python3
import csv
import os
import tempfile
import unittest

import scrape_ioverlander


class TestScrapeIOverlander(unittest.TestCase):

    def test_resolve_country_code(self):
        self.assertEqual(scrape_ioverlander.resolve_country_code("CAN"), "CAN")
        self.assertEqual(scrape_ioverlander.resolve_country_code("canada"), "CAN")
        self.assertEqual(scrape_ioverlander.resolve_country_code("USA"), "USA")
        self.assertEqual(scrape_ioverlander.resolve_country_code("United States"), "USA")
        self.assertEqual(scrape_ioverlander.resolve_country_code("Albania"), "ALB")

    def test_extract_place_uuids_from_html(self):
        sample_html = """
        <div>
            <a href="/places/bcedcbea-a3ee-4129-a2bb-8e84b8a71fe0">McDonald Creek</a>
            <a href="/places/f8137266-e23a-455b-b8ac-49fa4e0f88d9">BC - Greeny Lake</a>
            <a href="/places/new">New Place</a>
            <a href="/places/bcedcbea-a3ee-4129-a2bb-8e84b8a71fe0">Duplicate link</a>
        </div>
        """
        uuids = scrape_ioverlander.extract_place_uuids_from_html(sample_html)
        self.assertEqual(len(uuids), 2)
        self.assertIn("bcedcbea-a3ee-4129-a2bb-8e84b8a71fe0", uuids)
        self.assertIn("f8137266-e23a-455b-b8ac-49fa4e0f88d9", uuids)
        self.assertNotIn("new", uuids)

    def test_parse_popup_html(self):
        sample_popup = """
        <div class="mapPopup">
          <div class="d-flex align-items-center">
            <img alt="" src="/assets/icons-big/wild-camp.png" width="25" height="25" />
            <h1 class="h6 ms-2 mb-0">
              <a target="_blank" href="/places/test-uuid">McDonald Creek &amp; Stone Mountain</a> | Wild Camping
            </h1>
          </div>
          <div class="mapPopupSub">
            <div>
              Verified:
              2 months ago
            </div>
            <div>
              GPS: <strong>58.69521, -124.8886</strong>
            </div>
            <div>
              Elevation:
                947 masl
            </div>
          </div>
          <div class="prose text-break" lang="en"><p>Beautiful place across MacDonald Creek...</p></div>
        </div>
        """
        poi = scrape_ioverlander.parse_popup_html("test-uuid", sample_popup)
        self.assertIsNotNone(poi)
        self.assertEqual(poi["Id"], "test-uuid")
        self.assertEqual(poi["Name"], "McDonald Creek & Stone Mountain")
        self.assertEqual(poi["Category"], "Wild Camping")
        self.assertEqual(poi["Latitude"], "58.69521")
        self.assertEqual(poi["Longitude"], "-124.8886")
        self.assertEqual(poi["Altitude"], "947")
        self.assertEqual(poi["Date verified"], "2 months ago")
        self.assertEqual(poi["Description"], "Beautiful place across MacDonald Creek...")
        self.assertEqual(poi["Open"], "Yes")

    def test_is_within_bbox(self):
        self.assertTrue(scrape_ioverlander.is_within_bbox("50.0", "-120.0", 40.0, 60.0, -130.0, -110.0))
        self.assertFalse(scrape_ioverlander.is_within_bbox("50.0", "-120.0", 52.0, 60.0, -130.0, -110.0))
        self.assertFalse(scrape_ioverlander.is_within_bbox("invalid", "-120.0", 40.0, 60.0, -130.0, -110.0))

    def test_csv_export_format(self):
        sample_poi = {field: "" for field in scrape_ioverlander.CSV_FIELDS}
        sample_poi["Id"] = "12345"
        sample_poi["Name"] = "Test Spot"
        sample_poi["Category"] = "Wild Camping"
        sample_poi["Latitude"] = "45.123"
        sample_poi["Longitude"] = "-75.456"
        sample_poi["Description"] = "Great spot for testing."
        sample_poi["Open"] = "Yes"

        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".csv") as tmp:
            tmp_path = tmp.name

        try:
            with open(tmp_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=scrape_ioverlander.CSV_FIELDS)
                writer.writeheader()
                writer.writerow(sample_poi)

            with open(tmp_path, "r", encoding="utf-8") as f:
                reader = list(csv.DictReader(f))
                self.assertEqual(len(reader), 1)
                row = reader[0]
                self.assertEqual(row["Id"], "12345")
                self.assertEqual(row["Name"], "Test Spot")
                self.assertEqual(row["Latitude"], "45.123")
                self.assertEqual(row["Longitude"], "-75.456")
                self.assertEqual(row["Category"], "Wild Camping")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
