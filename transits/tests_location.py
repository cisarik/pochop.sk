from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import LocationLookupCache
from .models import SlovakCity
from .services.geocoding import (
    build_forward_cache_key,
    build_forward_query,
    build_reverse_cache_key,
    geocode_forward,
    geocode_reverse,
)
from .services.city_lookup import find_nearest_slovak_city
from .services.ip_geo import ip_to_location


@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'geo-tests',
    }
})
class GeocodingServiceTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_reverse_cache_key_rounds_coordinates(self):
        k1 = build_reverse_cache_key(48.1486001, 17.1077001, precision=5)
        k2 = build_reverse_cache_key(48.1486004, 17.1077004, precision=5)
        self.assertEqual(k1, k2)

    def test_forward_cache_key_is_normalized(self):
        q1 = build_forward_query(country=' Slovensko ', city=' Bratislava ', region='Bratislavský kraj')
        q2 = build_forward_query(country='slovensko', city='bratislava', region=' Bratislavský   kraj ')
        self.assertEqual(build_forward_cache_key(q1), build_forward_cache_key(q2))

    @patch('transits.services.geocoding.get_geocoding_provider')
    def test_geocode_reverse_uses_cache(self, provider_getter):
        provider = MagicMock()
        provider.reverse.return_value = {
            'country': 'Slovensko',
            'city': 'Bratislava',
            'region': 'Bratislavský kraj',
            'postcode': '811 01',
            'raw': {'ok': True},
        }
        provider_getter.return_value = provider

        first = geocode_reverse(48.1486, 17.1077)
        second = geocode_reverse(48.1486, 17.1077)

        self.assertEqual(first, second)
        self.assertEqual(provider.reverse.call_count, 1)

    @patch('transits.services.geocoding.get_geocoding_provider')
    def test_geocode_reverse_persists_single_db_row_per_day(self, provider_getter):
        provider = MagicMock()
        provider.reverse.return_value = {
            'country': 'Slovensko',
            'city': 'Bratislava',
            'region': 'Bratislavský kraj',
            'postcode': '811 01',
            'raw': {'ok': True},
        }
        provider_getter.return_value = provider

        geocode_reverse(48.1486001, 17.1077001)
        geocode_reverse(48.1486004, 17.1077004)

        self.assertEqual(
            LocationLookupCache.objects.filter(lookup_type='reverse').count(),
            1,
        )

    @patch('transits.services.geocoding.get_geocoding_provider')
    def test_geocode_forward_uses_cache(self, provider_getter):
        provider = MagicMock()
        provider.forward.return_value = {
            'lat': 48.1486,
            'lon': 17.1077,
            'country': 'Slovensko',
            'city': 'Bratislava',
            'region': 'Bratislavský kraj',
            'raw': {'ok': True},
        }
        provider_getter.return_value = provider

        first = geocode_forward(country='Slovensko', city='Bratislava', region='Bratislavský kraj')
        second = geocode_forward(country='Slovensko', city='Bratislava', region='Bratislavský kraj')

        self.assertEqual(first, second)
        self.assertEqual(provider.forward.call_count, 1)


class NearestCityLookupTests(TestCase):
    def setUp(self):
        SlovakCity.objects.create(
            name='Bratislava',
            district='Bratislava I',
            lat=48.1486,
            lon=17.1077,
        )
        SlovakCity.objects.create(
            name='Trnava',
            district='Trnava',
            lat=48.3774,
            lon=17.5883,
        )

    def test_find_nearest_city_for_bratislava_coordinates(self):
        nearest = find_nearest_slovak_city(48.1486, 17.1077)
        self.assertIsNotNone(nearest)
        self.assertEqual(nearest['name'], 'Bratislava')

    def test_find_nearest_city_returns_none_for_invalid_coords(self):
        nearest = find_nearest_slovak_city(999, 999)
        self.assertIsNone(nearest)


@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'geo-tests-api',
    }
})
class LocationApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(HTTP_HOST='pochop.sk')
        SlovakCity.objects.create(
            name='Bratislava',
            district='Bratislava I',
            lat=48.1486,
            lon=17.1077,
        )

    def test_reverse_validation_rejects_invalid_lat(self):
        response = self.client.post(
            reverse('transits:api_location_reverse'),
            data='{"lat": 150, "lon": 17.1}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_forward_validation_rejects_missing_city(self):
        response = self.client.post(
            reverse('transits:api_location_forward'),
            data='{"country": "Slovensko"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    @patch('transits.views.geocode_reverse')
    def test_reverse_endpoint_success(self, geocode_reverse_mock):
        geocode_reverse_mock.return_value = {
            'country': 'Slovensko',
            'city': 'Bratislava',
            'region': 'Bratislavský kraj',
            'postcode': '811 01',
            'raw': {'source': 'nominatim'},
        }

        response = self.client.post(
            reverse('transits:api_location_reverse'),
            data='{"lat": 48.1486, "lon": 17.1077}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode('utf-8'),
            {
                'country': 'Slovensko',
                'city': 'Bratislava',
                'region': 'Bratislavský kraj',
                'postcode': '811 01',
            },
        )

    @patch('transits.views.geocode_forward')
    def test_forward_endpoint_success(self, geocode_forward_mock):
        geocode_forward_mock.return_value = {
            'lat': 48.1486,
            'lon': 17.1077,
            'country': 'Slovensko',
            'city': 'Bratislava',
            'region': 'Bratislavský kraj',
            'raw': {'source': 'nominatim'},
        }

        response = self.client.post(
            reverse('transits:api_location_forward'),
            data='{"country": "Slovensko", "city": "Bratislava", "region": "Bratislavský kraj"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode('utf-8'),
            {
                'lat': 48.1486,
                'lon': 17.1077,
                'country': 'Slovensko',
                'city': 'Bratislava',
                'region': 'Bratislavský kraj',
            },
        )

    @patch('transits.views.ip_to_location')
    def test_from_ip_returns_204_when_no_location(self, ip_to_location_mock):
        ip_to_location_mock.return_value = None

        response = self.client.get(
            reverse('transits:api_location_from_ip'),
            HTTP_X_FORWARDED_FOR='203.0.113.1',
        )
        self.assertEqual(response.status_code, 204)

    @patch('transits.views.ip_to_location')
    def test_from_ip_prefers_public_ip_from_xff(self, ip_to_location_mock):
        ip_to_location_mock.return_value = {
            'country': 'Slovensko',
            'city': 'Bratislava',
            'region': 'Bratislavský kraj',
            'lat': 48.1486,
            'lon': 17.1077,
            'raw': {},
        }

        response = self.client.get(
            reverse('transits:api_location_from_ip'),
            HTTP_X_FORWARDED_FOR='10.0.0.10, 8.8.8.8',
            REMOTE_ADDR='172.16.0.1',
        )

        self.assertEqual(response.status_code, 200)
        ip_to_location_mock.assert_called_once_with('8.8.8.8')
        self.assertJSONEqual(
            response.content.decode('utf-8'),
            {
                'country': 'Slovensko',
                'city': 'Bratislava',
                'region': 'Bratislavský kraj',
                'lat': 48.1486,
                'lon': 17.1077,
            },
        )

    @patch('transits.views.ip_to_location')
    def test_from_ip_prefers_cloudflare_connecting_ip(self, ip_to_location_mock):
        ip_to_location_mock.return_value = {
            'country': 'Slovensko',
            'city': 'Bratislava',
            'region': '',
            'lat': 48.1486,
            'lon': 17.1077,
            'raw': {},
        }

        response = self.client.get(
            reverse('transits:api_location_from_ip'),
            HTTP_CF_CONNECTING_IP='8.8.4.4',
            HTTP_X_FORWARDED_FOR='10.0.0.10, 8.8.8.8',
            REMOTE_ADDR='172.16.0.1',
        )

        self.assertEqual(response.status_code, 200)
        ip_to_location_mock.assert_called_once_with('8.8.4.4')

    @patch('transits.views.ip_to_location')
    def test_from_ip_fills_city_from_nearest_gps_when_missing(self, ip_to_location_mock):
        ip_to_location_mock.return_value = {
            'country': 'Slovakia',
            'city': '',
            'region': '',
            'lat': 48.14865,
            'lon': 17.10775,
            'raw': {},
        }

        response = self.client.get(
            reverse('transits:api_location_from_ip'),
            HTTP_X_FORWARDED_FOR='8.8.8.8',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get('city'), 'Bratislava')
        self.assertEqual(payload.get('country'), 'Slovakia')

    @patch('transits.views.ip_to_location')
    def test_from_ip_uses_nearest_city_for_country_code_sk(self, ip_to_location_mock):
        ip_to_location_mock.return_value = {
            'country': 'SK',
            'city': 'Unknown',
            'region': '',
            'lat': 48.1486,
            'lon': 17.1077,
            'raw': {},
        }

        response = self.client.get(
            reverse('transits:api_location_from_ip'),
            HTTP_X_FORWARDED_FOR='8.8.8.8',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get('city'), 'Bratislava')
        self.assertEqual(payload.get('country'), 'SK')


@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'geo-tests-ip',
    }
})
class IpGeoServiceTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch('transits.services.ip_geo.requests.get')
    def test_ip_to_location_uses_cache(self, requests_get_mock):
        response_mock = MagicMock()
        response_mock.status_code = 200
        response_mock.json.return_value = {
            'country_name': 'Slovakia',
            'city': 'Bratislava',
            'region': 'Bratislavský kraj',
            'latitude': 48.1486,
            'longitude': 17.1077,
        }
        requests_get_mock.return_value = response_mock

        first = ip_to_location('8.8.8.8')
        second = ip_to_location('8.8.8.8')

        self.assertEqual(first, second)
        self.assertEqual(requests_get_mock.call_count, 1)

    @patch('transits.services.ip_geo.requests.get')
    def test_ip_to_location_returns_none_on_upstream_error(self, requests_get_mock):
        response_mock = MagicMock()
        response_mock.status_code = 500
        response_mock.json.return_value = {}
        requests_get_mock.return_value = response_mock

        result = ip_to_location('8.8.4.4')
        self.assertIsNone(result)

    @patch('transits.services.ip_geo.requests.get')
    def test_ip_to_location_persists_single_db_row_per_day(self, requests_get_mock):
        response_mock = MagicMock()
        response_mock.status_code = 200
        response_mock.json.return_value = {
            'country_name': 'Slovakia',
            'city': 'Bratislava',
            'region': 'Bratislavský kraj',
            'latitude': 48.1486,
            'longitude': 17.1077,
        }
        requests_get_mock.return_value = response_mock

        ip_to_location('8.8.8.8')
        ip_to_location('8.8.8.8')

        self.assertEqual(
            LocationLookupCache.objects.filter(lookup_type='ip').count(),
            1,
        )
