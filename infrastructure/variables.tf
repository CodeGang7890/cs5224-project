variable "project_id" {
  description = "GCP project ID."
  type        = string
  default     = "cs5224-project-508705"
}

variable "region" {
  description = "Region for every resource."
  type        = string
  default     = "asia-southeast1"
}

variable "image_tags" {
  description = <<-EOT
    Image tag per service, e.g. { "configuration-service" = "abc1234" }.
    Images are pulled from the Artifact Registry repo. A service that is missing
    from the map (or has an empty tag) runs the placeholder image instead.
  EOT
  type        = map(string)
  default     = {}
}

variable "placeholder_image" {
  description = "Image used by services that have no image tag yet."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}
