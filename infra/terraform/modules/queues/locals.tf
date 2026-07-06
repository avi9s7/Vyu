locals {
  workloads = {
    ingestion = {
      visibility_timeout_seconds = 300
    }
    research = {
      visibility_timeout_seconds = 600
    }
    synthesis = {
      visibility_timeout_seconds = 900
    }
    export = {
      visibility_timeout_seconds = 300
    }
  }
}
