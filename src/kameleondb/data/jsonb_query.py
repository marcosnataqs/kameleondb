"""PostgreSQL JSONB query builder for KameleonDB.

Provides CRUD operations using PostgreSQL's native JSONB type.
All field data is stored in a single JSONB column on kdb_records.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Boolean, Integer, Numeric, cast, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from kameleondb.core.types import QueryResult
from kameleondb.exceptions import FieldNotFoundError, QueryError, RecordNotFoundError
from kameleondb.schema.models import FieldDefinition, Record

if TYPE_CHECKING:
    from sqlalchemy import Engine


def generate_uuid() -> str:
    """Generate a new UUID as string."""
    return str(uuid4())


def utc_now() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc)


class JSONBQuery:
    """PostgreSQL JSONB-first query builder.

    Provides CRUD operations where all field data is stored in a single
    JSONB column, providing semantic locality and better agent reasoning.
    """

    # Operator mapping for filters
    OPERATORS: dict[str, str] = {
        "eq": "=",
        "ne": "!=",
        "gt": ">",
        "gte": ">=",
        "lt": "<",
        "lte": "<=",
        "like": "LIKE",
        "ilike": "ILIKE",
        "in": "IN",
        "is_null": "IS NULL",
    }

    def __init__(
        self,
        engine: Engine,
        entity_id: str,
        entity_name: str,
        fields: list[FieldDefinition],
    ) -> None:
        """Initialize JSONB query builder.

        Args:
            engine: SQLAlchemy engine (must be PostgreSQL)
            entity_id: Entity definition ID
            entity_name: Entity name (for error messages)
            fields: List of active field definitions
        """
        self._engine = engine
        self._entity_id = entity_id
        self._entity_name = entity_name
        self._fields = {f.name: f for f in fields}
        self._field_names = set(self._fields.keys())
        # Mapping from logical name to storage column name (for renamed fields)
        self._name_to_column = {f.name: f.column_name for f in fields}
        self._column_to_name = {f.column_name: f.name for f in fields}
        # System columns available on all records
        self._system_columns = {"id", "created_at", "updated_at", "created_by"}
        self._all_columns = self._field_names | self._system_columns

    def _get_field(self, name: str) -> FieldDefinition:
        """Get field definition by name."""
        if name not in self._fields:
            raise FieldNotFoundError(name, self._entity_name, sorted(self._field_names))
        return self._fields[name]

    def _serialize_value(self, value: Any, field_type: str) -> Any:
        """Serialize a value for JSONB storage.

        PostgreSQL JSONB handles most types natively. We only need special
        handling for datetime (stored as ISO string).
        """
        if value is None:
            return None

        if field_type == "datetime":
            if isinstance(value, datetime):
                return value.isoformat()
            return str(value)
        elif field_type == "json":
            # Already a dict/list, JSONB will handle it
            return value
        elif field_type == "bool":
            return bool(value)
        elif field_type == "int":
            return int(value)
        elif field_type == "float":
            return float(value)
        else:
            # string, text, uuid - store as-is
            return value

    def _deserialize_value(self, value: Any, field_type: str) -> Any:
        """Deserialize a value from JSONB.

        PostgreSQL JSONB returns native types, minimal deserialization needed.
        """
        if value is None:
            return None

        if field_type == "datetime":
            # Stored as ISO string, return as-is (or parse if needed)
            return value
        elif field_type == "bool":
            return bool(value)
        elif field_type == "int":
            return int(value) if value is not None else None
        elif field_type == "float":
            return float(value) if value is not None else None
        else:
            return value

    def _record_to_dict(self, record: Record) -> dict[str, Any]:
        """Convert a record to a dictionary."""
        result: dict[str, Any] = {
            "id": record.id,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            "created_by": record.created_by,
        }

        # Merge JSONB data, translating column names to logical names
        if record.data:
            for column_name, value in record.data.items():
                # Translate column name to logical name (handles renamed fields)
                logical_name = self._column_to_name.get(column_name, column_name)
                if logical_name in self._field_names:
                    result[logical_name] = value

        # Add None for fields without values
        for field_name in self._field_names:
            if field_name not in result:
                result[field_name] = None

        return result

    def _validate_fields(self, data: dict[str, Any]) -> None:
        """Validate that all fields in data exist."""
        for field in data:
            if field not in self._all_columns:
                raise FieldNotFoundError(field, self._entity_name, sorted(self._field_names))

    def _serialize_record_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Serialize all field data for JSONB storage.

        Uses column_name (storage key) instead of logical name for JSONB keys.
        This supports field renaming where the logical name changes but the
        storage key remains the same.
        """
        jsonb_data = {}
        for field_name, value in data.items():
            if field_name in self._system_columns:
                continue  # Skip system columns
            field = self._get_field(field_name)
            # Use column_name for storage (handles renamed fields)
            column_name = self._name_to_column.get(field_name, field_name)
            jsonb_data[column_name] = self._serialize_value(value, field.field_type)
        return jsonb_data

    def insert(
        self,
        data: dict[str, Any],
        created_by: str | None = None,
    ) -> str:
        """Insert a new record.

        Args:
            data: Record data (field: value pairs)
            created_by: Who created this record

        Returns:
            The new record ID
        """
        self._validate_fields(data)

        record_id = generate_uuid()
        now = utc_now()

        try:
            with Session(self._engine) as session:
                # Serialize all field data to JSONB
                jsonb_data = self._serialize_record_data(data)

                # Create the record with JSONB data
                record = Record(
                    id=record_id,
                    entity_id=self._entity_id,
                    data=jsonb_data,  # All fields in one JSONB column
                    created_at=now,
                    updated_at=now,
                    created_by=created_by,
                    is_deleted=False,
                )
                session.add(record)
                session.commit()

            return record_id
        except FieldNotFoundError:
            raise
        except Exception as e:
            raise QueryError(f"Failed to insert record: {e}") from e

    def insert_many(
        self,
        records: list[dict[str, Any]],
        created_by: str | None = None,
    ) -> list[str]:
        """Insert multiple records.

        Args:
            records: List of record data dicts
            created_by: Who created these records

        Returns:
            List of new record IDs
        """
        if not records:
            return []

        # Validate all records first
        for rec in records:
            self._validate_fields(rec)

        record_ids = []
        now = utc_now()

        try:
            with Session(self._engine) as session:
                for record_data in records:
                    record_id = generate_uuid()
                    record_ids.append(record_id)

                    # Serialize all field data to JSONB
                    jsonb_data = self._serialize_record_data(record_data)

                    # Create the record
                    record = Record(
                        id=record_id,
                        entity_id=self._entity_id,
                        data=jsonb_data,
                        created_at=now,
                        updated_at=now,
                        created_by=created_by,
                        is_deleted=False,
                    )
                    session.add(record)

                session.commit()

            return record_ids
        except FieldNotFoundError:
            raise
        except Exception as e:
            raise QueryError(f"Failed to insert records: {e}") from e

    def find(
        self,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        order_desc: bool = False,
        limit: int | None = None,
        offset: int | None = None,
    ) -> QueryResult:
        """Find records matching filters.

        Args:
            filters: Filter conditions
            order_by: Field to order by
            order_desc: Whether to order descending
            limit: Maximum records to return
            offset: Records to skip

        Returns:
            QueryResult with matching records
        """
        try:
            with Session(self._engine) as session:
                # Base query for records
                query = (
                    session.query(Record)
                    .filter(Record.entity_id == self._entity_id)
                    .filter(Record.is_deleted == False)  # noqa: E712
                )

                # Apply filters using JSONB operators
                if filters:
                    for field_name, value in filters.items():
                        if field_name in self._system_columns:
                            # Filter on record's own columns
                            column = getattr(Record, field_name, None)
                            if column is not None:
                                if isinstance(value, dict) and "op" in value:
                                    query = self._apply_system_filter(
                                        query, column, value["op"], value.get("value")
                                    )
                                else:
                                    query = query.filter(column == value)
                        else:
                            # Filter on JSONB data
                            if field_name not in self._fields:
                                raise FieldNotFoundError(
                                    field_name, self._entity_name, sorted(self._field_names)
                                )

                            field = self._fields[field_name]

                            if isinstance(value, dict) and "op" in value:
                                query = self._apply_jsonb_filter(
                                    query, field, value["op"], value.get("value")
                                )
                            else:
                                # Simple equality using containment operator
                                serialized = self._serialize_value(value, field.field_type)
                                # Use @> containment operator (uses GIN index efficiently)
                                # Use column_name (storage key) for JSONB access, not logical name
                                query = query.filter(
                                    Record.data.op("@>")(
                                        cast({field.column_name: serialized}, JSONB)
                                    )
                                )

                # Get total count before pagination
                total_count = query.count()

                # Apply ordering
                if order_by:
                    if order_by in self._system_columns:
                        column = getattr(Record, order_by)
                        query = query.order_by(column.desc() if order_desc else column)
                    elif order_by in self._fields:
                        # Order by JSONB field
                        field = self._fields[order_by]
                        # Extract field from JSONB and cast to appropriate type
                        jsonb_expr = self._get_jsonb_expression(field)
                        query = query.order_by(jsonb_expr.desc() if order_desc else jsonb_expr)
                    else:
                        raise FieldNotFoundError(
                            order_by, self._entity_name, sorted(self._field_names)
                        )

                # Apply pagination
                if offset is not None:
                    query = query.offset(offset)
                if limit is not None:
                    query = query.limit(limit)

                # Execute query
                records = query.all()

                # Convert to dicts
                result_records = [self._record_to_dict(record) for record in records]

            return QueryResult(
                records=result_records,
                total_count=total_count,
                limit=limit,
                offset=offset,
            )

        except FieldNotFoundError:
            raise
        except Exception as e:
            raise QueryError(f"Failed to execute query: {e}") from e

    def _get_jsonb_expression(self, field: FieldDefinition) -> Any:
        """Get PostgreSQL JSONB expression with proper type cast."""
        # Use column_name (storage key) for JSONB access, not logical name
        column_name = field.column_name
        field_type = field.field_type

        # Use ->> operator to extract as text, then cast to appropriate type
        if field_type == "int":
            return cast(Record.data[column_name].astext, type_=JSONB).cast(type_=Integer)
        elif field_type == "float":
            return cast(Record.data[column_name].astext, type_=Numeric())
        elif field_type == "bool":
            return cast(Record.data[column_name].astext, type_=Boolean)
        else:
            # String, text, datetime, uuid - extract as text
            return Record.data[column_name].astext

    def _apply_system_filter(self, query: Any, column: Any, op: str, value: Any) -> Any:
        """Apply a filter operator to a system column."""
        if op == "eq":
            return query.filter(column == value)
        elif op == "ne":
            return query.filter(column != value)
        elif op == "gt":
            return query.filter(column > value)
        elif op == "gte":
            return query.filter(column >= value)
        elif op == "lt":
            return query.filter(column < value)
        elif op == "lte":
            return query.filter(column <= value)
        elif op == "like":
            return query.filter(column.like(f"%{value}%"))
        elif op == "in":
            return query.filter(column.in_(value))
        elif op == "is_null":
            return query.filter(column.is_(None) if value else column.isnot(None))
        else:
            raise QueryError(f"Unknown operator '{op}'")

    def _apply_jsonb_filter(self, query: Any, field: FieldDefinition, op: str, value: Any) -> Any:
        """Apply a filter operator to a JSONB field.

        Uses PostgreSQL JSONB operators for efficient querying.
        Uses column_name (storage key) for JSONB access to support renamed fields.
        """
        # Use column_name for storage access, not logical name
        column_name = field.column_name
        field_type = field.field_type

        # Check existence first (unless is_null operator)
        if op != "is_null":
            # Use ? operator to check key exists
            query = query.filter(Record.data.op("?")(column_name))

        # Serialize value
        serialized_value = self._serialize_value(value, field_type) if value is not None else None

        # Build filter based on operator
        if op == "eq":
            # Use @> containment for equality (fast with GIN index)
            query = query.filter(Record.data.op("@>")(cast({column_name: serialized_value}, JSONB)))
        elif op == "ne":
            # Not equal: use ->> to extract and compare
            jsonb_field = Record.data[column_name].astext
            if field_type == "int":
                query = query.filter(cast(jsonb_field, Integer) != value)
            elif field_type == "float":
                query = query.filter(cast(jsonb_field, Numeric()) != value)
            elif field_type == "bool":
                query = query.filter(cast(jsonb_field, Boolean) != value)
            else:
                query = query.filter(jsonb_field != str(serialized_value))
        elif op in ("gt", "gte", "lt", "lte"):
            # Comparison operators: extract and cast
            jsonb_field = Record.data[column_name].astext
            if field_type == "int":
                casted = cast(jsonb_field, Integer)
            elif field_type == "float":
                casted = cast(jsonb_field, Numeric())  # type: ignore[arg-type]
            else:
                casted = jsonb_field

            if op == "gt":
                query = query.filter(casted > value)
            elif op == "gte":
                query = query.filter(casted >= value)
            elif op == "lt":
                query = query.filter(casted < value)
            elif op == "lte":
                query = query.filter(casted <= value)
        elif op == "like" or op == "ilike":
            # String pattern matching
            jsonb_field = Record.data[column_name].astext
            if op == "like":
                query = query.filter(jsonb_field.like(f"%{value}%"))
            else:
                query = query.filter(jsonb_field.ilike(f"%{value}%"))
        elif op == "in":
            # IN operator: check if value is in array
            # Serialize each value in the array
            serialized_values = [self._serialize_value(v, field_type) for v in value]
            # Use ->> to extract and check if in array
            jsonb_field = Record.data[column_name].astext
            if field_type == "int":
                casted = cast(jsonb_field, Integer)
            elif field_type == "float":
                casted = cast(jsonb_field, Numeric())  # type: ignore[arg-type]
            else:
                casted = jsonb_field
            query = query.filter(casted.in_(serialized_values))
        elif op == "is_null":
            # Check if field is missing or null
            if value:
                # Field should be null or missing
                query = query.filter(
                    ~Record.data.op("?")(column_name) | (Record.data[column_name].astext.is_(None))
                )
            else:
                # Field should exist and not be null
                query = query.filter(
                    Record.data.op("?")(column_name) & (Record.data[column_name].astext.isnot(None))
                )
        else:
            raise QueryError(f"Unknown operator '{op}'")

        return query

    def find_by_id(self, record_id: str) -> dict[str, Any] | None:
        """Find a record by ID.

        Args:
            record_id: Record ID

        Returns:
            Record dict or None if not found
        """
        try:
            with Session(self._engine) as session:
                record = (
                    session.query(Record)
                    .filter(Record.id == record_id)
                    .filter(Record.entity_id == self._entity_id)
                    .filter(Record.is_deleted == False)  # noqa: E712
                    .first()
                )

                if not record:
                    return None

                return self._record_to_dict(record)
        except Exception as e:
            raise QueryError(f"Failed to find record: {e}") from e

    def update(
        self,
        record_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update a record.

        Args:
            record_id: Record ID to update
            data: Fields to update

        Returns:
            Updated record dict
        """
        self._validate_fields(data)

        # Check record exists
        existing = self.find_by_id(record_id)
        if not existing:
            raise RecordNotFoundError(record_id, self._entity_name)

        now = utc_now()

        try:
            with Session(self._engine) as session:
                # Serialize new field data
                jsonb_updates = self._serialize_record_data(data)

                # Use PostgreSQL || operator to merge JSONB
                # This is efficient and native to PostgreSQL
                session.execute(
                    update(Record)
                    .where(Record.id == record_id)
                    .values(
                        data=Record.data.op("||")(cast(jsonb_updates, JSONB)),
                        updated_at=now,
                    )
                )

                session.commit()

            # Return updated record
            return self.find_by_id(record_id) or {}
        except FieldNotFoundError:
            raise
        except RecordNotFoundError:
            raise
        except Exception as e:
            raise QueryError(f"Failed to update record: {e}") from e

    def delete(self, record_id: str) -> bool:
        """Delete a record (soft delete).

        Args:
            record_id: Record ID to delete

        Returns:
            True if deleted
        """
        # Check record exists
        existing = self.find_by_id(record_id)
        if not existing:
            raise RecordNotFoundError(record_id, self._entity_name)

        try:
            with Session(self._engine) as session:
                # Soft delete the record
                session.execute(
                    update(Record)
                    .where(Record.id == record_id)
                    .values(is_deleted=True, updated_at=utc_now())
                )

                session.commit()

            return True
        except Exception as e:
            raise QueryError(f"Failed to delete record: {e}") from e

    def delete_many(
        self,
        filters: dict[str, Any] | None = None,
    ) -> int:
        """Delete multiple records matching filters.

        Args:
            filters: Filter conditions

        Returns:
            Number of records deleted
        """
        try:
            # First, find all matching records
            result = self.find(filters=filters)
            record_ids = [r["id"] for r in result.records]

            if not record_ids:
                return 0

            now = utc_now()

            with Session(self._engine) as session:
                # Soft delete records
                session.execute(
                    update(Record)
                    .where(Record.id.in_(record_ids))
                    .values(is_deleted=True, updated_at=now)
                )

                session.commit()

            return len(record_ids)
        except FieldNotFoundError:
            raise
        except Exception as e:
            raise QueryError(f"Failed to delete records: {e}") from e

    def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count records matching filters.

        Args:
            filters: Filter conditions

        Returns:
            Number of matching records
        """
        result = self.find(filters=filters)
        return result.total_count
