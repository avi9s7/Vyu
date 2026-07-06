## Summary

- Add Plan 4 Terraform skeleton: nine composable modules, `dev`/`staging`/`prod` environment roots, and provider lock files.
- Document remote-state bootstrap policy (encrypted S3 + DynamoDB lock) with `backend.hcl.example` per environment.
- Add `tests/infra/test_terraform_structure.py` to guard module layout, provider constraints, and forbidden plaintext secrets/local backends.

## Test plan

- [x] `uv run pytest tests/infra/test_terraform_structure.py -q` passes
- [x] `terraform -chdir=infra/terraform/environments/dev init -backend=false` succeeds
- [x] `terraform -chdir=infra/terraform/environments/dev fmt -recursive` clean
- [x] `terraform -chdir=infra/terraform/environments/dev validate` succeeds
- [ ] CI backend job green (existing unit + integration suite unaffected)
