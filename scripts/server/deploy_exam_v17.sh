#!/usr/bin/env bash
# Run as root on the existing server after pushing the reviewed release branch.
set -euo pipefail
umask 077
release_commit=${1:?release commit required}
previous_commit=${2:?previous commit required}
[[ "$release_commit" =~ ^[0-9a-f]{40}$ ]]
[[ "$previous_commit" =~ ^[0-9a-f]{40}$ ]]
cd /srv/app
test "$(git rev-parse HEAD)" = "$previous_commit"
git diff --quiet
git diff --cached --quiet
release_dir="/srv/backups/exam-v17-$(date -u +%Y%m%d-%H%M%SZ)"
install -d -m 700 "$release_dir"
git rev-parse HEAD > "$release_dir/previous-commit.txt"
sha256sum .env > "$release_dir/environment.sha256"
for service_name in api web; do
  docker inspect --format '{{.Image}}' "intelligent-qa-$service_name" > "$release_dir/previous-$service_name-image.txt"
  docker tag "$(cat "$release_dir/previous-$service_name-image.txt")" "intelligent-qa-$service_name:before-exam-v17-20261016"
done
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' < /dev/null > "$release_dir/database-before.dump"
test -s "$release_dir/database-before.dump"
docker compose exec -T db pg_restore --list < "$release_dir/database-before.dump" > "$release_dir/backup-catalog.txt"
counts_sql="SELECT json_build_object('users',(SELECT count(*) FROM users),'students',(SELECT count(*) FROM students),'teacher_profiles',(SELECT count(*) FROM teacher_profiles),'teaching_assignments',(SELECT count(*) FROM teaching_assignments),'exams',(SELECT count(*) FROM exams),'subject_scores',(SELECT count(*) FROM student_subject_scores),'question_scores',(SELECT count(*) FROM question_scores),'reports',(SELECT count(*) FROM diagnosis_reports));"
docker compose exec -T db psql -U postgres -d intelligent_qa -Atc "$counts_sql" < /dev/null > "$release_dir/counts-before.json"
printf 'backup_verified=%s\n' "$release_dir"
git fetch origin refs/heads/codex/exam-management-v17:refs/remotes/origin/codex/exam-management-v17 > "$release_dir/git-fetch.log" 2>&1
git merge-base --is-ancestor "$previous_commit" "$release_commit"
test "$(git rev-parse origin/codex/exam-management-v17)" = "$release_commit"
git switch --detach "$release_commit" > "$release_dir/git-switch.log" 2>&1
docker compose config > /dev/null
docker compose build api web < /dev/null > "$release_dir/build.log" 2>&1
printf 'build_verified=%s\n' "$release_commit"
# Migration 022 adds tables and permits unknown question maxima; no existing
# identities, score values, historical placements or authorizations are rewritten.
docker compose run --rm --no-deps api alembic upgrade head < /dev/null > "$release_dir/migration.log" 2>&1
docker compose exec -T db psql -U postgres -d intelligent_qa -Atc 'SELECT version_num FROM alembic_version' < /dev/null > "$release_dir/schema-version.txt"
test "$(cat "$release_dir/schema-version.txt")" = "022_exam_management"
docker compose up -d --no-deps --wait --wait-timeout 180 api web < /dev/null > "$release_dir/activate.log" 2>&1
docker compose exec -T nginx nginx -t < /dev/null >> "$release_dir/activate.log" 2>&1
docker compose exec -T nginx nginx -s reload < /dev/null >> "$release_dir/activate.log" 2>&1
curl --fail --silent --show-error --retry 8 --retry-delay 2 --retry-connrefused --max-time 10 http://127.0.0.1/api/v1/health > "$release_dir/health-after.json"
docker compose exec -T db psql -U postgres -d intelligent_qa -Atc "$counts_sql" < /dev/null > "$release_dir/counts-after.json"
expected_hash=$(sha256sum apps/api/app/services/exam_management.py | cut -d ' ' -f 1)
actual_hash=$(docker compose exec -T api python -c 'import hashlib;from pathlib import Path;print(hashlib.sha256(Path("/app/app/services/exam_management.py").read_bytes()).hexdigest())' < /dev/null)
test "$actual_hash" = "$expected_hash"
printf 'active_source_sha256=%s\n' "$actual_hash"
python3 - "$release_dir" <<'PY'
import json, sys
from pathlib import Path
directory = Path(sys.argv[1])
before = json.loads((directory / 'counts-before.json').read_text())
after = json.loads((directory / 'counts-after.json').read_text())
assert before == after, (before, after)
health = json.loads((directory / 'health-after.json').read_text())
assert health['status'] == 'ok' and health['environment'] == 'production'
assert health['model']['real_model_ready']
print('business_data_counts_unchanged=true')
print('production_health_verified=true')
print(json.dumps(after))
PY
sha256sum -c "$release_dir/environment.sha256"
docker compose ps --format '{{.Name}} {{.Status}}'
git rev-parse HEAD > "$release_dir/released-commit.txt"
printf 'release_verified=%s\n' "$release_commit"
