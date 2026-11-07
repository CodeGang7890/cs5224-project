resource "google_logging_metric" "cloud_run_http_errors" {
  name        = "cloud_run_http_errors"
  description = "Counts Cloud Run request log entries with an HTTP 4xx or 5xx response."
  filter      = <<-EOT
    resource.type="cloud_run_revision"
    httpRequest.status>=400
    httpRequest.status<600
  EOT

  metric_descriptor {
    metric_kind  = "DELTA"
    value_type   = "INT64"
    unit         = "1"
    display_name = "Cloud Run HTTP error responses"
  }
}

resource "google_monitoring_notification_channel" "alert_email" {
  count        = trimspace(var.alert_notification_email) == "" ? 0 : 1
  display_name = "Ansera Cloud Run HTTP error email"
  type         = "email"
  labels = {
    email_address = var.alert_notification_email
  }
}

resource "google_monitoring_alert_policy" "cloud_run_http_errors" {
  display_name = "Cloud Run: 10 HTTP errors in 5 minutes"
  combiner     = "OR"
  enabled      = true
  severity     = "WARNING"

  conditions {
    display_name = "At least 10 HTTP 4xx/5xx responses across Cloud Run services in 5 minutes"

    condition_threshold {
      filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.cloud_run_http_errors.name}\" AND resource.type=\"cloud_run_revision\""

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }

      comparison      = "COMPARISON_GT"
      threshold_value = 9
      duration        = "0s"
    }
  }

  notification_channels = trimspace(var.alert_notification_email) == "" ? [] : [google_monitoring_notification_channel.alert_email[0].name]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    mime_type = "text/markdown"
    content   = "Cloud Run request logs recorded at least 10 HTTP 4xx or 5xx responses in a five-minute aligned interval. Check Logs Explorer for `resource.type=\"cloud_run_revision\" AND httpRequest.status>=400 AND httpRequest.status<600`, then review the affected service and revision."
  }

  depends_on = [
    google_project_service.api,
    google_logging_metric.cloud_run_http_errors,
    google_monitoring_notification_channel.alert_email,
  ]
}
