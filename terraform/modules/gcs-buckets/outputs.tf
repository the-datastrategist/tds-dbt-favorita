output "bucket_names" {
  value = { for k, b in google_storage_bucket.buckets : k => b.name }
}

output "mlflow_bucket_name" {
  value = var.enable_mlflow_bucket ? google_storage_bucket.mlflow[0].name : null
}
