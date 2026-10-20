#!/usr/bin/env bash
# SSH as ubuntu; run with sudo -n bash after publishing the verified branch.
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
release_dir="/srv/backups/role-access-$(date -u +%Y%m%d-%H%M%SZ)"
install -d -m 700 "$release_dir"
git rev-parse HEAD > "$release_dir/previous-commit.txt"
sha256sum .env > "$release_dir/environment.sha256"
for service_name in api web; do
  docker inspect --format '{{.Image}}' "intelligent-qa-$service_name" > "$release_dir/previous-$service_name-image.txt"
  docker inspect --format '{{.Config.Image}}' "intelligent-qa-$service_name" > "$release_dir/previous-$service_name-reference.txt"
  docker tag "$(cat "$release_dir/previous-$service_name-image.txt")" "intelligent-qa-$service_name:before-$(basename "$release_dir")"
done
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
    for service_name in api web; do
      docker tag "$(cat "$release_dir/previous-$service_name-image.txt")" "$(cat "$release_dir/previous-$service_name-reference.txt")"
    done
    docker compose up -d --no-deps --no-build --wait --wait-timeout 180 api web > "$release_dir/rollback-services.log" 2>&1
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
counts_sql="SELECT json_build_object('users',(SELECT count(*) FROM users),'students',(SELECT count(*) FROM students),'teacher_profiles',(SELECT count(*) FROM teacher_profiles),'teaching_assignments',(SELECT count(*) FROM teaching_assignments),'exams',(SELECT count(*) FROM exams),'exam_query_policies',(SELECT count(*) FROM exam_query_policies),'exam_query_grants',(SELECT count(*) FROM exam_query_grants),'subject_scores',(SELECT count(*) FROM student_subject_scores),'question_scores',(SELECT count(*) FROM question_scores),'managed_reports',(SELECT count(*) FROM managed_reports),'user_roles',(SELECT count(*) FROM user_roles),'human_handoffs',(SELECT count(*) FROM human_handoffs),'handoff_messages',(SELECT count(*) FROM education_handoff_messages),'answer_tickets',(SELECT count(*) FROM answer_tickets));"
fingerprints_sql="SELECT json_build_object('user_roles',(SELECT md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.user_id, t.role_id), '')) FROM user_roles t),'teacher_profiles',(SELECT md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.id), '')) FROM teacher_profiles t),'policies',(SELECT md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.id), '')) FROM exam_query_policies t),'grants',(SELECT md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.id), '')) FROM exam_query_grants t),'administration',(SELECT md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.id), '')) FROM exam_administrations t));"
database_query() {
  docker compose exec -T db sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "$1"' sh "$1" < /dev/null
}
database_query "$counts_sql" > "$release_dir/counts-before.json"
database_query "$fingerprints_sql" > "$release_dir/fingerprints-before.json"
database_query 'SELECT version_num FROM alembic_version' > "$release_dir/schema-before.txt"
printf 'backup_verified=%s\n' "$release_dir"
git fetch origin refs/heads/codex/fix-role-access-flows:refs/remotes/origin/codex/fix-role-access-flows > "$release_dir/git-fetch.log" 2>&1
git merge-base --is-ancestor "$previous_commit" "$release_commit"
test "$(git rev-parse origin/codex/fix-role-access-flows)" = "$release_commit"
# No infrastructure changes, database migrations or data rewrites in this release.
git diff --quiet "$previous_commit" "$release_commit" -- docker-compose.yml infra apps/api/alembic
(umask 022; git switch --detach "$release_commit") > "$release_dir/git-switch.log" 2>&1
source_switched=true
docker compose config > /dev/null
docker compose build api web < /dev/null > "$release_dir/build.log" 2>&1
printf 'build_verified=%s\n' "$release_commit"
activation_started=true
docker compose up -d --no-deps --wait --wait-timeout 180 api web < /dev/null > "$release_dir/activate.log" 2>&1
docker compose exec -T nginx nginx -t < /dev/null >> "$release_dir/activate.log" 2>&1
docker compose exec -T nginx nginx -s reload < /dev/null >> "$release_dir/activate.log" 2>&1
curl --fail --silent --show-error --retry 8 --retry-delay 2 --retry-connrefused --max-time 10 http://127.0.0.1/api/v1/health > "$release_dir/health-after.json"
for source_file in api/deps.py core/access_scope.py api/v1/endpoints/platform.py api/v1/endpoints/management_details.py services/learning_workbench.py services/answer_workbench.py; do
  expected_hash=$(sha256sum "apps/api/app/$source_file" | cut -d ' ' -f 1)
  actual_hash=$(docker compose exec -T api sha256sum "/app/app/$source_file" < /dev/null | cut -d ' ' -f 1)
  test "$actual_hash" = "$expected_hash"
  printf '%s  %s\n' "$actual_hash" "$source_file" >> "$release_dir/active-api-source.sha256"
done
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
for label in ['PASSWORD_CHANGE_REQUIRED', 'canClaim', 'role-access-20261020', '查看学情']:
    assert label in javascript, label
mini_api = get('/answer-workbench/mini-api.js').decode()
assert '返回工作台' in mini_api and 'onclick="boot()"' in mini_api
for route in ['/answer-workbench/mini.html', '/answer-workbench/web.html']:
    assert 'mini-api.js?v=role-access-20261020' in get(route).decode()
assert 'web.css?v=role-access-20261020' in get('/answer-workbench/web.html').decode()
for name in ['mini-api.js', 'mini.html', 'web.html', 'web.css']:
    route = '/answer-workbench/' + name
    served_hash = hashlib.sha256(get(route)).hexdigest()
    image_hash = subprocess.check_output(['docker', 'compose', 'exec', '-T', 'web', 'sha256sum', '/usr/share/nginx/html' + route], text=True).split()[0]
    assert served_hash == image_hash, route
routes = ['/admin/school?tab=teachers', '/admin/school?tab=students', '/admin/school?tab=exam-management', '/admin/reports', '/mini']
for route in routes:
    assert get(route).decode() == index, route
print(json.dumps({'verified_assets': assets, 'verified_routes': routes, 'role_access_and_password_bridge_ui_verified': True}))
PY
database_query "$counts_sql" > "$release_dir/counts-after.json"
database_query "$fingerprints_sql" > "$release_dir/fingerprints-after.json"
database_query 'SELECT version_num FROM alembic_version' > "$release_dir/schema-after.txt"
cmp "$release_dir/schema-before.txt" "$release_dir/schema-after.txt"
python3 - "$release_dir" <<'PY'
import json
import sys
from pathlib import Path

directory = Path(sys.argv[1])
for name in ['counts', 'fingerprints']:
    before = json.loads((directory / f'{name}-before.json').read_text())
    after = json.loads((directory / f'{name}-after.json').read_text())
    assert before == after, (name, before, after)
health = json.loads((directory / 'health-after.json').read_text())
assert health['status'] == 'ok' and health['environment'] == 'production'
assert health['model']['real_model_ready']
print('business_data_counts_and_permission_fingerprints_unchanged=true')
print('production_health_verified=true')
PY
sha256sum -c "$release_dir/environment.sha256"
docker compose ps --format '{{.Name}} {{.Status}}'
git rev-parse HEAD > "$release_dir/released-commit.txt"
printf 'release_verified=%s; evidence=%s\n' "$release_commit" "$release_dir"
