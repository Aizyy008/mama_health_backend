from rest_framework import serializers


class NearbyHospitalsQuerySerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    radius = serializers.IntegerField(required=False, default=5000, min_value=100, max_value=50000)


class HospitalSerializer(serializers.Serializer):
    place_id = serializers.CharField(allow_null=True)
    name = serializers.CharField(allow_null=True)
    address = serializers.CharField(allow_null=True)
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)
    rating = serializers.FloatField(allow_null=True, required=False)
    is_open_now = serializers.BooleanField(allow_null=True, required=False)
