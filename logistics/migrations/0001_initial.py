# Generated by Django 5.2.4 on 2025-07-17 17:21

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DeliveryPartner",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("api_endpoint", models.URLField()),
                ("api_key", models.CharField(max_length=255)),
                ("service_areas", models.JSONField(default=list)),
                ("pricing_structure", models.JSONField(default=dict)),
                ("is_active", models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name="ShippingZone",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("areas", models.JSONField(default=list)),
                ("base_fee", models.DecimalField(decimal_places=2, max_digits=10)),
                ("per_kg_fee", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "free_shipping_threshold",
                    models.DecimalField(decimal_places=2, max_digits=12, null=True),
                ),
                ("estimated_delivery_days", models.IntegerField()),
                ("is_active", models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name="Shipment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("tracking_number", models.CharField(max_length=100)),
                ("pickup_address", models.JSONField(default=dict)),
                ("delivery_address", models.JSONField(default=dict)),
                ("estimated_delivery", models.DateTimeField()),
                ("actual_delivery", models.DateTimeField(null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("in_transit", "In Transit"),
                            ("delivered", "Delivered"),
                            ("failed", "Failed"),
                        ],
                        max_length=32,
                    ),
                ),
                ("tracking_history", models.JSONField(default=list)),
                ("delivery_fee", models.DecimalField(decimal_places=2, max_digits=10)),
                ("notes", models.TextField(blank=True)),
                (
                    "delivery_partner",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="logistics.deliverypartner",
                    ),
                ),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE, to="orders.order"
                    ),
                ),
            ],
        ),
    ]
