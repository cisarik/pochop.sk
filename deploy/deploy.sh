#!/bin/bash
# ════════════════════════════════════════
# Pochop.sk — Deploy script
# Spusti na serveri: sudo bash deploy.sh
# ════════════════════════════════════════
set -e

APP_DIR="/var/www/pochop"

echo "╔══════════════════════════════════╗"
echo "║      Pochop.sk Deploy            ║"
echo "╚══════════════════════════════════╝"

# 1. Virtualenv + dependencies
echo ""
echo "[1/6] Python virtualenv + dependencies..."
if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# 2. Migrácie
echo ""
echo "[2/6] Databázové migrácie..."
cd "$APP_DIR"
"$APP_DIR/venv/bin/python" manage.py migrate --noinput

# 3. Collectstatic
echo ""
echo "[3/6] Statické súbory..."
"$APP_DIR/venv/bin/python" manage.py collectstatic --noinput

# 4. Populate data
echo ""
echo "[4/6] Naplnenie databázy..."
"$APP_DIR/venv/bin/python" manage.py populate_transits
"$APP_DIR/venv/bin/python" manage.py populate_cities

# 5. Permissions
echo ""
echo "[5/6] Oprávnenia..."
chown -R www-data:www-data "$APP_DIR"

# 6. Systemd + Nginx
echo ""
echo "[6/6] Služby..."
cp "$APP_DIR/deploy/pochop.service" /etc/systemd/system/
cp "$APP_DIR/deploy/pochop-moment.service" /etc/systemd/system/
cp "$APP_DIR/deploy/pochop-moment.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable pochop
systemctl enable --now pochop-moment.timer
systemctl restart pochop

cp "$APP_DIR/deploy/nginx-pochop.conf" /etc/nginx/sites-available/pochop
ln -sf /etc/nginx/sites-available/pochop /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo ""
echo "╔══════════════════════════════════╗"
echo "║   ✅ Deploy hotový!              ║"
echo "╚══════════════════════════════════╝"
echo ""
echo "Ďalšie kroky:"
echo "  1. HTTPS: sudo certbot --nginx -d pochop.sk -d www.pochop.sk"
echo "  2. Superuser: cd $APP_DIR && venv/bin/python manage.py createsuperuser"
echo "  3. Logs: journalctl -u pochop -f"
echo ""
