from rest_framework import serializers
from django.db import transaction
from .models import Article, ArticleAttached, ArticleReviewer, Event, Schedule, Topic

class ArticleAttachedSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArticleAttached
        fields = ["article_attached_id", "article_attached_url", "article_attached_version", "article_attached_created_at"]

class ArticleCorrectedVersionSerializer(serializers.ModelSerializer):
    corrected_version = serializers.SerializerMethodField()
    class Meta:
        model = Article
        fields = ["article_id", "article_subject", "article_description", "corrected_version"]

    def get_corrected_version(self, obj):
        latest = obj.attachments.filter(article_attached_active=True, article_attached_delete=False).order_by("-article_attached_created_at").first()
        if latest:
            return ArticleAttachedSerializer(latest).data
        return None

class AvalInputSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000)

class CorrectedVersionUploadSerializer(serializers.Serializer):
    corrected_pdf = serializers.FileField()

class FinalSubmissionSerializer(serializers.Serializer):
    final_pdf = serializers.FileField()
    copyright_pdf = serializers.FileField()

class ArticleReorderSerializer(serializers.Serializer):
    ordered_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False
    )


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            "event_id",
            "event_name",
            "event_description",
            "event_address",
            "event_date",
        ]


class TopicSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Topic
        fields = ["topic_id", "topic_subject", "topic_description"]


class ScheduleSerializer(serializers.ModelSerializer):
    topic = TopicSummarySerializer(source="topic_id", read_only=True, allow_null=True)

    class Meta:
        model = Schedule
        fields = ["schedule_id", "schedule_hour", "application_id", "topic_id", "topic"]


class EventDetailSerializer(EventSerializer):
    schedule = ScheduleSerializer(source="schedule_items", many=True, read_only=True)
    topics = serializers.SerializerMethodField()

    class Meta(EventSerializer.Meta):
        fields = EventSerializer.Meta.fields + ["schedule", "topics"]

    def get_topics(self, obj):
        topics_by_id = {
            item.topic_id_id: item.topic_id
            for item in obj.schedule_items.all()
            if item.topic_id_id is not None
        }
        topics = sorted(topics_by_id.values(), key=lambda topic: topic.topic_subject)
        return TopicSummarySerializer(topics, many=True).data


class EventScheduleInputSerializer(serializers.Serializer):
    schedule_id = serializers.IntegerField(required=False, min_value=1)
    topic_id = serializers.PrimaryKeyRelatedField(
        queryset=Topic.objects.filter(topic_active=True, topic_delete=False)
    )
    schedule_hour = serializers.TimeField()


class EventWriteSerializer(serializers.ModelSerializer):
    schedule = EventScheduleInputSerializer(many=True, required=False)

    class Meta:
        model = Event
        fields = [
            "event_name",
            "event_description",
            "event_address",
            "event_date",
            "schedule",
        ]

    def validate_schedule(self, schedule_data):
        schedule_ids = [
            item["schedule_id"]
            for item in schedule_data
            if "schedule_id" in item
        ]
        if len(schedule_ids) != len(set(schedule_ids)):
            raise serializers.ValidationError("No se puede repetir una actividad del cronograma.")
        if schedule_ids and self.instance is None:
            raise serializers.ValidationError("No se pueden enviar IDs de cronograma al crear un evento.")
        if self.instance is not None:
            existing_ids = set(
                self.instance.schedule_items.values_list("schedule_id", flat=True)
            )
            if not set(schedule_ids).issubset(existing_ids):
                raise serializers.ValidationError("El cronograma contiene una actividad que no pertenece a este evento.")
        return schedule_data

    @transaction.atomic
    def create(self, validated_data):
        schedule_data = validated_data.pop("schedule", [])
        event = Event.objects.create(**validated_data)
        self._create_schedule(event, schedule_data)
        return event

    @transaction.atomic
    def update(self, instance, validated_data):
        schedule_data = validated_data.pop("schedule", None)
        existing_schedules = None
        if schedule_data is not None:
            existing_schedules = {
                item.schedule_id: item
                for item in instance.schedule_items.all()
            }
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if schedule_data is not None:
            instance.schedule_items.all().delete()
            self._create_schedule(instance, schedule_data, existing_schedules)
        return instance

    @staticmethod
    def _create_schedule(event, schedule_data, existing_schedules=None):
        Schedule.objects.bulk_create([
            Schedule(
                event=event,
                topic_id=item["topic_id"],
                schedule_hour=item["schedule_hour"],
                application_id=(
                    existing_schedules[item["schedule_id"]].application_id
                    if existing_schedules and "schedule_id" in item
                    else None
                ),
            )
            for item in schedule_data
        ])