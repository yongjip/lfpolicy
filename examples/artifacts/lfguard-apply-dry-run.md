Dry run: no changes applied.

### lfguard plan

- Total changes: 3
- Safe changes: 3
- Destructive changes: 0

| ID | Safety | Action | Target | Reason |
| --- | --- | --- | --- | --- |
| change_001 | safe | lf_tag.add_values | lf_tag:sensitivity | LF-Tag is missing allowed values |
| change_002 | safe | resource_tag.add_values | table:database=analytics:table=orders | Resource is missing desired LF-Tag assignments |
| change_003 | safe | grant.add_permissions | arn:aws:iam::111122223333:role/Analyst -> lf_tag_policy:resource_type=TABLE:expression=domain=sales,sensitivity=internal\|public | Principal is missing desired Lake Formation permissions |
