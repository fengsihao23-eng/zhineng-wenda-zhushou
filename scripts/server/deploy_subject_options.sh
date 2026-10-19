#!/usr/bin/env bash
# Connect as ubuntu and execute with sudo -n bash after publishing the tested commit.
set -euo pipefail
umask 077
release_commit=${1:?release commit required}
previous_commit=${2:?previous commit required}
[[ "$release_commit" =~ ^[0-9a-f]{40}$ ]]
[[ "$previous_commit" =~ ^[0-9a-f]{40}$ ]]
test "$(id -u)" = 0
cd /srv/app
test "$(git rev-parse HEAD)" = "$previous_commit"
git diff --quiet
git diff --cached --quiet
release_dir="/srv/backups/subject-options-$(date -u +%Y%m%d-%H%M%SZ)"
install -d -m 700 "$release_dir"
git rev-parse HEAD > "$release_dir/previous-commit.txt"
sha256sum .env > "$release_dir/environment.sha256"
docker inspect --format '{{.Id}}' intelligent-qa-api > "$release_dir/api-container-before.txt"
docker inspect --format '{{.Image}}' intelligent-qa-web > "$release_dir/previous-web-image.txt"
docker inspect --format '{{.Config.Image}}' intelligent-qa-web > "$release_dir/previous-web-reference.txt"
docker tag "$(cat "$release_dir/previous-web-image.txt")" "intelligent-qa-web:before-$(basename "$release_dir")"
source_switched=false
activation_started=false
rollback() {
  local failure=$?
  trap - ERR
  set +e
  if "$source_switched"; then
    (umask 022; git switch --detach "$previous_commit") > "$release_dir/rollback-source.log" 2>&1
  fi
  if "$activation_started"; then
    docker tag "$(cat "$release_dir/previous-web-image.txt")" "$(cat "$release_dir/previous-web-reference.txt")"
    docker compose up -d --no-deps --no-build --wait --wait-timeout 120 web > "$release_dir/rollback-services.log" 2>&1
    docker compose exec -T nginx nginx -s reload < /dev/null >> "$release_dir/rollback-services.log" 2>&1
    curl --fail --silent --show-error --max-time 15 http://127.0.0.1/api/v1/health > "$release_dir/rollback-health.json"
  fi
  printf 'release_failed=%s; evidence=%s\n' "$failure" "$release_dir"
  exit "$failure"
}
trap rollback ERR
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' < /dev/null > "$release_dir/database-before.dump"
test -s "$release_dir/database-before.dump"
docker compose exec -T db pg_restore --list < "$release_dir/database-before.dump" > "$release_dir/backup-catalog.txt"
counts_sql="SELECT json_build_object('users',(SELECT count(*) FROM users),'students',(SELECT count(*) FROM students),'teacher_profiles',(SELECT count(*) FROM teacher_profiles),'exams',(SELECT count(*) FROM exams),'exam_query_policies',(SELECT count(*) FROM exam_query_policies),'exam_query_grants',(SELECT count(*) FROM exam_query_grants),'subject_scores',(SELECT count(*) FROM student_subject_scores),'question_scores',(SELECT count(*) FROM question_scores),'managed_reports',(SELECT count(*) FROM managed_reports));"
database_counts() {
  docker compose exec -T db sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "$1"' sh "$counts_sql" < /dev/null
}
fingerprints_sql="SELECT json_build_object('administration',(SELECT md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.id), '')) FROM exam_administrations t),'policies',(SELECT md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.id), '')) FROM exam_query_policies t),'grants',(SELECT md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.id), '')) FROM exam_query_grants t));"
database_fingerprints() {
  docker compose exec -T db sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "$1"' sh "$fingerprints_sql" < /dev/null
}
database_counts > "$release_dir/counts-before.json"
database_fingerprints > "$release_dir/fingerprints-before.json"
printf 'backup_verified=%s\n' "$release_dir"
git fetch origin refs/heads/codex/fix-exam-report-subjects:refs/remotes/origin/codex/fix-exam-report-subjects > "$release_dir/git-fetch.log" 2>&1
git merge-base --is-ancestor "$previous_commit" "$release_commit"
test "$(git rev-parse origin/codex/fix-exam-report-subjects)" = "$release_commit"
# This release changes only frontend behavior; backend and deployment configuration must match.
git diff --quiet "$previous_commit" "$release_commit" -- apps/api docker-compose.yml infra
(umask 022; git switch --detach "$release_commit") > "$release_dir/git-switch.log" 2>&1
source_switched=true
docker compose config > /dev/null
docker compose build web < /dev/null > "$release_dir/build.log" 2>&1
printf 'build_verified=%s\n' "$release_commit"
activation_started=true
docker compose up -d --no-deps --wait --wait-timeout 120 web < /dev/null > "$release_dir/activate.log" 2>&1
docker compose exec -T nginx nginx -t < /dev/null >> "$release_dir/activate.log" 2>&1
docker compose exec -T nginx nginx -s reload < /dev/null >> "$release_dir/activate.log" 2>&1
curl --fail --silent --show-error --retry 6 --retry-delay 2 --retry-connrefused --max-time 10 http://127.0.0.1/api/v1/health > "$release_dir/health-after.json"
python3 - <<'PY' > "$release_dir/frontend-after.json"
import hashlib
import json
import re
import subprocess
from urllib.request import Request, urlopen

def get(route):
    with urlopen(Request('http://127.0.0.1' + route, headers={'Accept-Encoding': 'identity'}), timeout=15) as response:
        assert response.status == 200, route
        return response.read()

index = get('/').decode()
assets = sorted(set(re.findall(r'(?:src|href)="(/assets/[^"?#]+\.(?:js|css))"', index)))
assert assets and any(asset.endswith('.js') for asset in assets)
for asset in assets:
    assert re.fullmatch(r'/assets/[A-Za-z0-9_.-]+\.(js|css)', asset), asset
    served_hash = hashlib.sha256(get(asset)).hexdigest()
    image_hash = subprocess.check_output(['docker', 'compose', 'exec', '-T', 'web', 'sha256sum', '/usr/share/nginx/html' + asset], text=True).split()[0]
    assert served_hash == image_hash, asset
javascript = '\n'.join(get(asset).decode() for asset in assets if asset.endswith('.js'))
for label in ['本次考试已配置：', '其他科目请先在考试列表的', '（本次考试未配置）', '作文批改报告', '成绩科目', '报告科目']:
    assert label in javascript, label
routes = ['/admin/school?tab=teachers', '/admin/school?tab=students', '/admin/school?tab=exam-management', '/admin/reports', '/admin/prompts', '/mini']
for route in routes:
    assert get(route).decode() == index, route
assert b'<html' in get('/answer-workbench/admin.html').lower()
assert b'<html' in get('/answer-workbench/mini.html').lower()
print(json.dumps({'verified_assets': assets, 'verified_routes': routes, 'subject_option_ui_verified': True}))
PY
database_counts > "$release_dir/counts-after.json"
database_fingerprints > "$release_dir/fingerprints-after.json"
cmp "$release_dir/fingerprints-before.json" "$release_dir/fingerprints-after.json"
python3 - "$release_dir" <<'PY'
import json
import sys
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
PY
test "$(docker inspect --format '{{.Id}}' intelligent-qa-api)" = "$(cat "$release_dir/api-container-before.txt")"
sha256sum -c "$release_dir/environment.sha256"
docker compose ps --format '{{.Name}} {{.Status}}'
git rev-parse HEAD > "$release_dir/released-commit.txt"
printf 'release_verified=%s; evidence=%s\n' "$release_commit" "$release_dir"
