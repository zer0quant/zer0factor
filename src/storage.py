from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


class FactorStorage:
    def __init__(self, factor_dir: Path, db_path: Path):
        self._factor_dir = Path(factor_dir)
        self._db_path = Path(db_path)
        self._factor_dir.mkdir(parents=True, exist_ok=True)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with duckdb.connect(str(self._db_path)) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS factor_registry (
                    factor_name VARCHAR PRIMARY KEY,
                    last_updated TIMESTAMP DEFAULT now()
                )
            """)

    def write(self, factor_name: str, df: pd.DataFrame) -> None:
        required = {"trade_date", "ts_code", "value"}
        if not required.issubset(df.columns):
            raise ValueError(f"DataFrame must have columns: {required}")

        for date, group in df.groupby("trade_date"):
            partition = self._factor_dir / factor_name / f"date={date}"
            partition.mkdir(parents=True, exist_ok=True)
            table = pa.Table.from_pandas(
                group[["ts_code", "value"]].reset_index(drop=True),
                preserve_index=False,
            )
            pq.write_table(table, partition / "data.parquet")

        with duckdb.connect(str(self._db_path)) as con:
            con.execute("""
                INSERT INTO factor_registry (factor_name) VALUES (?)
                ON CONFLICT (factor_name) DO UPDATE SET last_updated = now()
            """, [factor_name])

    def read(
        self,
        factor_name: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        factor_path = self._factor_dir / factor_name
        if not factor_path.exists():
            raise FileNotFoundError(f"Factor '{factor_name}' not found")

        pattern = str(factor_path / "date=*" / "data.parquet")
        where = []
        params: list = [pattern]
        if start_date:
            where.append("date >= ?")
            params.append(start_date)
        if end_date:
            where.append("date <= ?")
            params.append(end_date)

        sql = (
            "SELECT date AS trade_date, ts_code, value"
            " FROM read_parquet(?, hive_partitioning=true)"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY trade_date, ts_code"

        return duckdb.connect().execute(sql, params).fetchdf()

    def list_factors(self) -> list[str]:
        with duckdb.connect(str(self._db_path)) as con:
            rows = con.execute(
                "SELECT factor_name FROM factor_registry ORDER BY factor_name"
            ).fetchall()
        return [r[0] for r in rows]
