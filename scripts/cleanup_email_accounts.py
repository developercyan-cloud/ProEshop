#!/usr/bin/env python3
"""
Safe ProEshop email-account cleanup for Railway / SQLite.

Default mode is DRY RUN: it prints the number of rows that would be affected.
To delete, pass --confirm-delete-email-accounts.

It backs up the SQLite database using SQLite's backup API (safe with WAL mode)
before making changes. Only these tables may be changed:
  - sessions: sessions whose telegram_id equals an email_accounts.account_id
  - telegram_verification_handoffs: handoffs belonging to those account IDs
  - email_accounts: all registered email-account rows

All orders, payments, purchases, order events, audit logs, users, carts, balances,
and every other table are left untouched.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DB = "/data/shopcart.db"


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def count_by_ids(conn: sqlite3.Connection, table: str, column: str, ids: list[str]) -> int:
    if not ids or not table_exists(conn, table) or column not in columns(conn, table):
        return 0
    total = 0
    # Keep below SQLite's usual bind-variable limit.
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        marks = ",".join("?" for _ in chunk)
        total += conn.execute(
            f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IN ({marks})',
            chunk,
        ).fetchone()[0]
    return total


def delete_by_ids(conn: sqlite3.Connection, table: str, column: str, ids: list[str]) -> int:
    if not ids or not table_exists(conn, table) or column not in columns(conn, table):
        return 0
    total = 0
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        marks = ",".join("?" for _ in chunk)
        cur = conn.execute(
            f'DELETE FROM "{table}" WHERE "{column}" IN ({marks})',
            chunk,
        )
        total += cur.rowcount if cur.rowcount >= 0 else 0
    return total


def make_backup(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"shopcart-before-email-account-cleanup-{stamp}.db"
    # SQLite backup API creates a consistent snapshot even when WAL is enabled.
    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    destination = sqlite3.connect(str(backup_path), timeout=30)
    try:
        source.backup(destination)
        destination.commit()
    finally:
        destination.close()
        source.close()
    # Verify the backup can be opened and passes an integrity check.
    verify = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True, timeout=30)
    try:
        result = verify.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"La copia de seguridad no pasó integrity_check: {result}")
    finally:
        verify.close()
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Limpieza segura de cuentas de correo de ProEshop.")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"Ruta SQLite (por defecto: {DEFAULT_DB})")
    parser.add_argument(
        "--backup-dir",
        default="/data/backups",
        help="Directorio de copias de seguridad (por defecto: /data/backups)",
    )
    parser.add_argument(
        "--confirm-delete-email-accounts",
        action="store_true",
        help="Confirma la eliminación real. Sin esta opción solo se hace una vista previa.",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"ERROR: no existe la base de datos: {db_path}", file=sys.stderr)
        print("No se ha borrado nada. Comprueba la ruta y el volumen persistente de Railway.", file=sys.stderr)
        return 2

    # Open with a normal connection so the script respects the DB's normal SQLite behavior.
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")

    try:
        required = {"email_accounts"}
        missing = [name for name in required if not table_exists(conn, name)]
        if missing:
            print("ERROR: faltan tablas esperadas: " + ", ".join(missing), file=sys.stderr)
            print("No se ha borrado nada. Este script no parece corresponder a esta versión de ProEshop.", file=sys.stderr)
            return 3

        account_cols = columns(conn, "email_accounts")
        if "account_id" not in account_cols:
            print("ERROR: email_accounts no tiene la columna account_id.", file=sys.stderr)
            print("No se ha borrado nada.", file=sys.stderr)
            return 3

        account_ids = [
            str(row[0]) for row in conn.execute(
                'SELECT account_id FROM email_accounts WHERE account_id IS NOT NULL'
            ).fetchall()
        ]
        account_count = conn.execute("SELECT COUNT(*) FROM email_accounts").fetchone()[0]
        sessions_count = count_by_ids(conn, "sessions", "telegram_id", account_ids)
        handoffs_count = count_by_ids(conn, "telegram_verification_handoffs", "account_id", account_ids)

        print("\n=== ProEshop: limpieza segura de cuentas registradas ===")
        print(f"Base de datos: {db_path}")
        print(f"Cuentas en email_accounts que se eliminarían: {account_count}")
        print(f"Sesiones asociadas que se revocarían: {sessions_count}")
        print(f"Códigos temporales asociados que se eliminarían: {handoffs_count}")
        print("\nNO se modifican pedidos, pagos, compras, historial, auditoría, users, carts ni balances.")
        print("Tampoco se elimina ninguna tabla ni se borra el volumen de Railway.")

        if not args.confirm_delete_email_accounts:
            print("\nVISTA PREVIA: no se ha eliminado ni modificado ninguna fila.")
            print("Para ejecutar la limpieza real, vuelve a correr el script añadiendo:")
            print("  --confirm-delete-email-accounts")
            return 0

        if account_count == 0:
            print("\nNo hay cuentas registradas en email_accounts. No hay nada que eliminar.")
            return 0

        print("\nCreando y verificando copia de seguridad antes de borrar...")
        backup_path = make_backup(db_path, Path(args.backup_dir))
        print(f"Copia verificada: {backup_path}")

        # Use a transaction for the actual cleanup. Only the three tables above can change.
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Re-read IDs after backup, in case the database changed between preview and deletion.
            current_ids = [
                str(row[0]) for row in conn.execute(
                    'SELECT account_id FROM email_accounts WHERE account_id IS NOT NULL'
                ).fetchall()
            ]
            current_count = conn.execute("SELECT COUNT(*) FROM email_accounts").fetchone()[0]
            if current_count != account_count or set(current_ids) != set(account_ids):
                raise RuntimeError(
                    "Las cuentas cambiaron después de la vista previa. No se ha borrado nada; "
                    "vuelve a ejecutar el script para revisar el nuevo estado."
                )

            deleted_sessions = delete_by_ids(conn, "sessions", "telegram_id", current_ids)
            deleted_handoffs = delete_by_ids(conn, "telegram_verification_handoffs", "account_id", current_ids)
            deleted_accounts = conn.execute("DELETE FROM email_accounts").rowcount
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        remaining = conn.execute("SELECT COUNT(*) FROM email_accounts").fetchone()[0]
        if remaining != 0:
            print(
                f"ADVERTENCIA: quedan {remaining} filas en email_accounts. "
                "Revisa la base de datos antes de volver a ejecutar.",
                file=sys.stderr,
            )
            return 4

        print("\nLIMPIEZA COMPLETADA")
        print(f"Cuentas eliminadas: {deleted_accounts}")
        print(f"Sesiones revocadas: {deleted_sessions}")
        print(f"Códigos temporales eliminados: {deleted_handoffs}")
        print(f"Respaldo previo: {backup_path}")
        print("Pedidos, pagos e historial permanecen en sus tablas originales.")
        return 0

    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        print("Si ya se creó una copia de seguridad, consérvala. No borres el volumen.", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
