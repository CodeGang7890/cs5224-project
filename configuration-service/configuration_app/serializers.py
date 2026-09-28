from rest_framework import serializers


class RandomNumberSerializer(serializers.Serializer):
    value = serializers.IntegerField(min_value=1, max_value=10)
