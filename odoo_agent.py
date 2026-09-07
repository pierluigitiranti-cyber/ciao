import re

from typing import Any, Dict, List, Optional, Tuple

from app.services.odoo_validator import (
    odoo_validator
)

from app.services.odoo_partner_resolver import (
    odoo_partner_resolver
)

from app.services.request_context import (
    get_odoo_client
)


# ==========================================================
# UTILITY
# ==========================================================

def _normalize_parameters(
    plan: Dict[str, Any]
) -> Dict[str, Any]:

    parameters = (
        plan.get(
            "parameters"
        )
        or {}
    )

    if not isinstance(
        parameters,
        dict
    ):
        parameters = {}

    model = parameters.get(
        "model"
    )

    method = parameters.get(
        "method"
    )

    params = parameters.get(
        "params"
    )

    if not isinstance(
        params,
        dict
    ):
        params = {}

    planner_args = parameters.get(
        "args"
    )

    planner_kwargs = parameters.get(
        "kwargs"
    )

    if (
        isinstance(
            planner_args,
            list
        )
        and planner_args
    ):

        first_arg = planner_args[0]

        if (
            "domain" not in params
            and isinstance(
                first_arg,
                list
            )
        ):

            params["domain"] = first_arg

    if isinstance(
        planner_kwargs,
        dict
    ):

        for key, value in planner_kwargs.items():

            if key in {
                "args",
                "kwargs",
            }:
                continue

            if key not in params:

                params[key] = value

    for key, value in parameters.items():

        if key in {
            "model",
            "method",
            "params",
            "args",
            "kwargs",
        }:
            continue

        if key not in params:

            params[key] = value

    params.pop(
        "args",
        None
    )

    params.pop(
        "kwargs",
        None
    )

    return {

        "model":
            model,

        "method":
            method,

        "params":
            params,

    }


# ==========================================================
# PARTNER FILTER DETECTION
# ==========================================================

PARTNER_NAME_FIELDS = {

    "partner_id.name",

    "partner_id.display_name",

    "commercial_partner_id.name",

    "commercial_partner_id.display_name",

}


def _domain_contains_partner_name_filter(
    value: Any
) -> bool:

    if not isinstance(
        value,
        list
    ):
        return False

    if (
        len(value) >= 3
        and isinstance(
            value[0],
            str
        )
    ):

        field = (
            value[0]
            .strip()
        )

        if field in PARTNER_NAME_FIELDS:

            return True

    for item in value:

        if _domain_contains_partner_name_filter(
            item
        ):

            return True

    return False


def _contains_partner_name_filter(
    domain
) -> bool:

    return _domain_contains_partner_name_filter(
        domain
    )


def _needs_partner_resolver(
    method: str,
    params: Dict[str, Any]
) -> bool:

    if method == "read_group":

        return False

    domain = (
        params.get(
            "domain"
        )
        or []
    )

    return _contains_partner_name_filter(
        domain
    )


# ==========================================================
# AGGREGAZIONI
# ==========================================================

def _extract_aggregate_fields(
    fields: Any
) -> List[Tuple[str, str]]:

    result: List[
        Tuple[str, str]
    ] = []

    if not isinstance(
        fields,
        list
    ):
        return result

    for field in fields:

        if not isinstance(
            field,
            str
        ):
            continue

        if ":" not in field:
            continue

        base, aggregate = (
            field.split(
                ":",
                1
            )
        )

        base = (
            base.strip()
        )

        aggregate = (
            aggregate
            .strip()
            .lower()
        )

        if not base:
            continue

        if aggregate not in {
            "sum",
            "avg",
            "min",
            "max",
            "count",
            "count_distinct",
        }:
            continue

        result.append(
            (
                base,
                aggregate
            )
        )

    return result


def _get_aggregation_value(
    row: Dict[str, Any],
    field: str,
    aggregate: str
) -> Any:

    if not isinstance(
        row,
        dict
    ):
        return None

    candidates = [

        f"{field}_{aggregate}",

        f"{field}:{aggregate}",

        field,

    ]

    for candidate in candidates:

        if candidate in row:

            return row.get(
                candidate
            )

    return None


def _row_has_requested_aggregates(
    row: Dict[str, Any],
    aggregate_fields: List[Tuple[str, str]]
) -> bool:

    if not aggregate_fields:

        return True

    if not isinstance(
        row,
        dict
    ):
        return False

    for field, aggregate in (
        aggregate_fields
    ):

        value = (
            _get_aggregation_value(
                row,
                field,
                aggregate
            )
        )

        if value is None:

            return False

    return True


def _rows_have_requested_aggregates(
    rows: List[Any],
    aggregate_fields: List[Tuple[str, str]]
) -> bool:

    if not aggregate_fields:

        return True

    if not isinstance(
        rows,
        list
    ):
        return False

    if not rows:

        return False

    for row in rows:

        if not _row_has_requested_aggregates(
            row,
            aggregate_fields
        ):

            return False

    return True


# ==========================================================
# ORDERBY READ_GROUP
# ==========================================================

def _normalize_read_group_orderby(
    params: Dict[str, Any]
) -> Dict[str, Any]:

    if not isinstance(
        params,
        dict
    ):

        return params

    orderby = params.get(
        "orderby"
    )

    if not isinstance(
        orderby,
        str
    ):
        return params

    orderby = orderby.strip()

    if not orderby:
        return params

    parts = (
        orderby.split()
    )

    field = (
        parts[0]
    )

    direction = (
        parts[1].lower()
        if len(parts) > 1
        else "asc"
    )

    if direction not in {
        "asc",
        "desc",
    }:

        direction = "asc"

    if field == "__count":

        params["orderby"] = (
            f"__count {direction}"
        )

        return params

    aggregate_suffixes = (
        "_sum",
        "_avg",
        "_min",
        "_max",
        "_count",
    )

    for suffix in aggregate_suffixes:

        if field.endswith(
            suffix
        ):

            base_field = field[
                :-
                len(suffix)
            ]

            if base_field:

                print(
                    "\n===== ORDERBY NORMALIZATION ====="
                )

                print(
                    "ORIGINAL ORDERBY:",
                    orderby
                )

                print(
                    "NORMALIZED ORDERBY:",
                    f"{base_field} {direction}"
                )

                params["orderby"] = (
                    f"{base_field} {direction}"
                )

                return params

    params["orderby"] = (
        f"{field} {direction}"
    )

    return params


# ==========================================================
# NORMALIZZAZIONE RISPOSTA ODOO
# ==========================================================

def _normalize_odoo_result(
    result: Any,
    method: str,
    params: Dict[str, Any]
) -> Dict[str, Any]:

    raw_result = result

    if not isinstance(
        result,
        dict
    ):

        return {

            "type":
                "unknown",

            "records":
                [],

            "count":
                0,

            "aggregation":
                [],

            "pagination": {

                "total_records":
                    0,

                "returned_records":
                    0,

                "limit":
                    0,

                "offset":
                    0,

                "pages":
                    0,

                "has_more":
                    False,

            },

            "raw_result":
                raw_result,

        }

    payload = result.get(
        "result"
    )

    # ======================================================
    # SEARCH COUNT
    # ======================================================

    if method == "search_count":

        count = 0

        if isinstance(
            payload,
            dict
        ):

            value = payload.get(
                "data",
                0
            )

            if isinstance(
                value,
                bool
            ):

                count = int(
                    value
                )

            elif isinstance(
                value,
                (int, float)
            ):

                count = int(
                    value
                )

        elif isinstance(
            payload,
            (int, float)
        ):

            count = int(
                payload
            )

        return {

            "type":
                "count",

            "records":
                [],

            "count":
                count,

            "aggregation":
                [],

            "pagination": {

                "total_records":
                    count,

                "returned_records":
                    0,

                "limit":
                    0,

                "offset":
                    0,

                "pages":
                    1,

                "has_more":
                    False,

            },

            "raw_result":
                raw_result,

        }

    # ======================================================
    # READ GROUP
    # ======================================================

    if method == "read_group":

        rows = []

        if isinstance(
            payload,
            list
        ):

            rows = [

                row

                for row in payload

                if isinstance(
                    row,
                    dict
                )

            ]

        requested_limit = params.get(
            "limit"
        )

        offset = params.get(
            "offset",
            0
        )

        if not isinstance(
            offset,
            int
        ):

            offset = 0

        if offset < 0:

            offset = 0

        if (
            isinstance(
                requested_limit,
                int
            )
            and requested_limit > 0
        ):

            returned_rows = rows[
                offset:
                offset + requested_limit
            ]

            limit_value = (
                requested_limit
            )

        else:

            returned_rows = rows[
                offset:
            ]

            limit_value = len(
                returned_rows
            )

        total_groups = len(
            rows
        )

        has_more = (
            offset
            + len(
                returned_rows
            )
            < total_groups
        )

        pages = (

            (

                total_groups
                + limit_value
                - 1

            )
            // limit_value

            if limit_value > 0

            else 1
        )

        aggregate_fields = (
            _extract_aggregate_fields(
                params.get(
                    "fields",
                    []
                )
            )
        )

        available = (
            _rows_have_requested_aggregates(
                returned_rows,
                aggregate_fields
            )
        )

        return {

            "type":
                "aggregation",

            "records":
                returned_rows,

            "count":
                total_groups,

            "aggregation":
                returned_rows,

            "pagination": {

                "total_records":
                    total_groups,

                "returned_records":
                    len(
                        returned_rows
                    ),

                "limit":
                    limit_value,

                "offset":
                    offset,

                "pages":
                    pages,

                "has_more":
                    has_more,

            },

            "aggregation_meta": {

                "requested":
                    aggregate_fields,

                "available":
                    available,

            },

            "raw_result":
                raw_result,

        }

    # ======================================================
    # SEARCH READ / ALTRI
    # ======================================================

    data = []

    pagination = {}

    if isinstance(
        payload,
        dict
    ):

        data = payload.get(
            "data",
            []
        )

        pagination = (
            payload.get(
                "pagination"
            )
            or {}
        )

    if not isinstance(
        data,
        list
    ):

        data = []

    if not isinstance(
        pagination,
        dict
    ):

        pagination = {}

    total = pagination.get(
        "total"
    )

    limit = pagination.get(
        "limit"
    )

    offset = pagination.get(
        "offset",
        0
    )

    pages = pagination.get(
        "pages"
    )

    if total is None:

        total = len(
            data
        )

    if limit is None:

        limit = len(
            data
        )

    if pages is None:

        pages = (

            (

                total
                + limit
                - 1

            )
            // limit

            if limit > 0

            else 1
        )

    has_more = pagination.get(
        "has_more"
    )

    if has_more is None:

        has_more = (
            offset
            + len(data)
            < total
        )

    return {

        "type":
            "records",

        "records":
            data,

        "count":
            total,

        "aggregation":
            [],

        "pagination": {

            "total_records":
                total,

            "returned_records":
                len(data),

            "limit":
                limit,

            "offset":
                offset,

            "pages":
                pages,

            "has_more":
                has_more,

        },

        "raw_result":
            raw_result,

    }


# ==========================================================
# USER INTENT / DOMAIN SANITIZATION
# ==========================================================

def _sanitize_domain_against_user_intent(
    model: str,
    domain: Any,
    user_message: str
) -> Any:

    return domain


# ==========================================================
# PARTNER RESOLUTION
# ==========================================================

async def _resolve_partner_domain(
    model: str,
    method: str,
    params: Dict[str, Any]
) -> Tuple[
    str,
    str,
    Dict[str, Any]
]:

    if not isinstance(
        params,
        dict
    ):

        params = {}

    domain = (
        params.get(
            "domain"
        )
        or []
    )

    if not _contains_partner_name_filter(
        domain
    ):

        return (
            model,
            method,
            params
        )

    print(
        "\n===== PARTNER RESOLUTION ====="
    )

    print(
        "PARTNER NAME FILTER DETECTED"
    )

    print(
        "DOMAIN BEFORE RESOLUTION:",
        domain
    )

    resolved_parameters = {

        "model":
            model,

        "method":
            method,

        "params":
            params,

    }

    resolved_parameters = (
        await odoo_partner_resolver.resolve(
            resolved_parameters
        )
    )

    resolved_model = (
        resolved_parameters.get(
            "model",
            model
        )
    )

    resolved_method = (
        resolved_parameters.get(
            "method",
            method
        )
    )

    resolved_params = (
        resolved_parameters.get(
            "params",
            {}
        )
    )

    if not isinstance(
        resolved_params,
        dict
    ):

        resolved_params = {}

    print(
        "DOMAIN AFTER RESOLUTION:",
        resolved_params.get(
            "domain",
            []
        )
    )

    return (
        resolved_model,
        resolved_method,
        resolved_params
    )


# ==========================================================
# NESTED PARAMETER NORMALIZATION
# ==========================================================

def _normalize_nested_params(
    params: Dict[str, Any]
) -> Dict[str, Any]:

    if not isinstance(
        params,
        dict
    ):

        return {}

    nested_args = params.get(
        "args"
    )

    if (
        isinstance(
            nested_args,
            list
        )
        and nested_args
        and "domain" not in params
        and isinstance(
            nested_args[0],
            list
        )
    ):

        params["domain"] = (
            nested_args[0]
        )

    nested_kwargs = params.get(
        "kwargs"
    )

    if isinstance(
        nested_kwargs,
        dict
    ):

        for key, value in nested_kwargs.items():

            if key not in params:

                params[key] = value

    params.pop(
        "args",
        None
    )

    params.pop(
        "kwargs",
        None
    )

    return params


# ==========================================================
# PYTHON AGGREGATION
# ==========================================================

def _group_value(
    record: Dict[str, Any],
    groupby_field: str
) -> Tuple[Any, Any]:

    value = record.get(
        groupby_field
    )

    if isinstance(
        value,
        list
    ):

        if len(value) >= 2:

            return (
                value[0],
                value
            )

        if len(value) == 1:

            return (
                value[0],
                value
            )

        return (
            False,
            value
        )

    if isinstance(
        value,
        dict
    ):

        group_id = (
            value.get(
                "id"
            )
        )

        return (
            group_id,
            value
        )

    return (
        value,
        value
    )


def _safe_number(
    value: Any
) -> float:

    if isinstance(
        value,
        bool
    ):

        return float(
            int(value)
        )

    if isinstance(
        value,
        (int, float)
    ):

        return float(
            value
        )

    try:

        return float(
            value
        )

    except (
        TypeError,
        ValueError
    ):

        return 0.0


def _sort_aggregation_rows(
    rows: List[Dict[str, Any]],
    orderby: Optional[str]
) -> List[Dict[str, Any]]:

    if not isinstance(
        orderby,
        str
    ):

        return rows

    orderby = (
        orderby.strip()
    )

    if not orderby:

        return rows

    parts = (
        orderby.split()
    )

    field = parts[0]

    direction = (
        parts[1].lower()
        if len(parts) > 1
        else "asc"
    )

    reverse = (
        direction == "desc"
    )

    if field == "__count":

        return sorted(
            rows,
            key=lambda row:
                _safe_number(
                    row.get(
                        "__count",
                        0
                    )
                ),
            reverse=reverse
        )

    possible_keys = [

        field,

        f"{field}_sum",

        f"{field}_avg",

        f"{field}_min",

        f"{field}_max",

        f"{field}_count",

        f"{field}:sum",

        f"{field}:avg",

        f"{field}:min",

        f"{field}:max",

    ]

    real_key = None

    for candidate in possible_keys:

        if any(
            candidate in row
            for row in rows
        ):

            real_key = candidate

            break

    if real_key is None:

        return rows

    return sorted(
        rows,
        key=lambda row:
            _safe_number(
                row.get(
                    real_key,
                    0
                )
            ),
        reverse=reverse
    )


async def _python_aggregate_read_group(
    odoo_client,
    model: str,
    domain: List[Any],
    fields: List[Any],
    groupby: List[Any],
    orderby: Optional[str],
    limit: int,
    offset: int
) -> Dict[str, Any]:

    print(
        "\n===== PYTHON READ_GROUP AGGREGATION ====="
    )

    print(
        "MODEL:",
        model
    )

    print(
        "GROUPBY:",
        groupby
    )

    print(
        "DOMAIN:",
        domain
    )

    if not groupby:

        raise ValueError(
            "Impossibile eseguire l'aggregazione Python "
            "senza un campo di raggruppamento."
        )

    groupby_field = str(
        groupby[0]
    )

    aggregate_fields = (
        _extract_aggregate_fields(
            fields
        )
    )

    detail_fields = [
        groupby_field
    ]

    for field, _aggregate in aggregate_fields:

        if field not in detail_fields:

            detail_fields.append(
                field
            )

    if "id" not in detail_fields:

        detail_fields.insert(
            0,
            "id"
        )

    page_size = 10000
    page_offset = 0

    all_records: List[
        Dict[str, Any]
    ] = []

    while True:

        payload = {

            "domain":
                domain,

            "fields":
                detail_fields,

            "limit":
                page_size,

            "offset":
                page_offset,

        }

        print(
            "\n===== PYTHON AGGREGATION PAGE ====="
        )

        print(
            "OFFSET:",
            page_offset
        )

        response = await (
            odoo_client.call(
                f"/api/{model}/search_read",
                body=payload
            )
        )

        if not isinstance(
            response,
            dict
        ):

            break

        result_payload = (
            response.get(
                "result",
                {}
            )
        )

        if not isinstance(
            result_payload,
            dict
        ):

            break

        records = (
            result_payload.get(
                "data",
                []
            )
        )

        if not isinstance(
            records,
            list
        ):

            records = []

        records = [

            record

            for record in records

            if isinstance(
                record,
                dict
            )

        ]

        all_records.extend(
            records
        )

        print(
            "PAGE RECORDS:",
            len(records)
        )

        pagination = (
            result_payload.get(
                "pagination",
                {}
            )
        )

        if not isinstance(
            pagination,
            dict
        ):

            pagination = {}

        total = pagination.get(
            "total"
        )

        if not isinstance(
            total,
            int
        ):

            total = len(
                all_records
            )

        if not records:

            break

        page_offset += len(
            records
        )

        if (
            page_offset >= total
            or len(records) < page_size
        ):

            break

    print(
        "\n===== PYTHON AGGREGATION DATASET ====="
    )

    print(
        "TOTAL RECORDS:",
        len(all_records)
    )

    groups: Dict[Any, Dict[str, Any]] = {}

    for record in all_records:

        group_id, group_value = (
            _group_value(
                record,
                groupby_field
            )
        )

        if group_id in {
            None,
            False,
        }:

            continue

        if group_id not in groups:

            groups[group_id] = {

                groupby_field:
                    group_value,

                "__count":
                    0,

                "_sums":
                    {},

                "_mins":
                    {},

                "_maxs":
                    {},

            }

        group = groups[
            group_id
        ]

        group["__count"] += 1

        for field, aggregate in (
            aggregate_fields
        ):

            value = record.get(
                field
            )

            numeric = _safe_number(
                value
            )

            if aggregate in {
                "sum",
                "avg",
            }:

                current = (
                    group[
                        "_sums"
                    ].get(
                        field,
                        0.0
                    )
                )

                group[
                    "_sums"
                ][
                    field
                ] = (
                    current
                    + numeric
                )

            if aggregate == "min":

                if field not in group[
                    "_mins"
                ]:

                    group[
                        "_mins"
                    ][
                        field
                    ] = numeric

                else:

                    group[
                        "_mins"
                    ][
                        field
                    ] = min(
                        group[
                            "_mins"
                        ][
                            field
                        ],
                        numeric
                    )

            if aggregate == "max":

                if field not in group[
                    "_maxs"
                ]:

                    group[
                        "_maxs"
                    ][
                        field
                    ] = numeric

                else:

                    group[
                        "_maxs"
                    ][
                        field
                    ] = max(
                        group[
                            "_maxs"
                        ][
                            field
                        ],
                        numeric
                    )

    rows = []

    for group in groups.values():

        row = {

            groupby_field:
                group.get(
                    groupby_field
                ),

            "__count":
                group.get(
                    "__count",
                    0
                ),

        }

        count = (
            group.get(
                "__count",
                0
            )
        )

        for field, aggregate in (
            aggregate_fields
        ):

            if aggregate == "sum":

                row[
                    f"{field}_sum"
                ] = (
                    group[
                        "_sums"
                    ].get(
                        field,
                        0.0
                    )
                )

            elif aggregate == "avg":

                total = (
                    group[
                        "_sums"
                    ].get(
                        field,
                        0.0
                    )
                )

                row[
                    f"{field}_avg"
                ] = (
                    total / count
                    if count > 0
                    else 0.0
                )

            elif aggregate == "min":

                row[
                    f"{field}_min"
                ] = (
                    group[
                        "_mins"
                    ].get(
                        field,
                        0.0
                    )
                )

            elif aggregate == "max":

                row[
                    f"{field}_max"
                ] = (
                    group[
                        "_maxs"
                    ].get(
                        field,
                        0.0
                    )
                )

            elif aggregate == "count":

                row[
                    f"{field}_count"
                ] = count

            elif aggregate == "count_distinct":

                row[
                    f"{field}_count_distinct"
                ] = count

        rows.append(
            row
        )

    rows = _sort_aggregation_rows(
        rows,
        orderby
    )

    total_groups = len(
        rows
    )

    if not isinstance(
        offset,
        int
    ):

        offset = 0

    if offset < 0:

        offset = 0

    if not isinstance(
        limit,
        int
    ) or limit <= 0:

        limit = 10

    returned_rows = rows[
        offset:
        offset + limit
    ]

    has_more = (
        offset
        + len(returned_rows)
        < total_groups
    )

    pages = (

        (

            total_groups
            + limit
            - 1

        )
        // limit

        if limit > 0

        else 1
    )

    print(
        "\n===== PYTHON AGGREGATION SUCCESS ====="
    )

    print(
        "TOTAL GROUPS:",
        total_groups
    )

    print(
        "RETURNED GROUPS:",
        len(returned_rows)
    )

    print(
        "ORDERBY:",
        orderby
    )

    return {

        "jsonrpc":
            "2.0",

        "id":
            None,

        "result":
            returned_rows,

        "_python_aggregation":
            True,

        "_pagination": {

            "total":
                total_groups,

            "limit":
                limit,

            "offset":
                offset,

            "pages":
                pages,

            "has_more":
                has_more,

        },

    }


# ==========================================================
# DYNAMIC FIELD RESOLUTION
# ==========================================================

DYNAMIC_SENSITIVE_FIELD_TOKENS = {

    "password",
    "passwd",
    "token",
    "secret",
    "private",
    "api_key",
    "apikey",
    "access_token",
    "session",
}


DYNAMIC_BINARY_FIELD_TYPES = {

    "binary",
}


DYNAMIC_INTERNAL_FIELD_NAMES = {

    "__last_update",

    "id",

    "create_uid",
    "write_uid",

}


DYNAMIC_INTERNAL_FIELD_TOKENS = {

    "checksum",

    "store_fname",

    "db_datas",

    "index_content",

}


DYNAMIC_RECENT_TERMS = [

    "ultimo",
    "ultimi",
    "ultime",
    "ultima",

    "recente",
    "recenti",

    "piu recente",
    "più recente",

    "piu recenti",
    "più recenti",

    "appena creato",
    "appena creati",

    "recentemente",

]


DYNAMIC_MODIFIED_TERMS = [

    "modificato",
    "modificati",
    "modificata",
    "modificate",

    "aggiornato",
    "aggiornati",
    "aggiornata",
    "aggiornate",

    "ultima modifica",
    "ultime modifiche",

    "recentemente modificato",
    "recentemente aggiornato",

]


def _dynamic_field_is_sensitive(
    field_name: str,
    field_meta: Dict[str, Any],
) -> bool:

    field_name = str(
        field_name or ""
    ).strip().lower()

    if not field_name:
        return True

    field_type = str(
        field_meta.get(
            "type",
            field_meta.get(
                "ttype",
                ""
            )
        )
        or ""
    ).lower()

    if field_type in DYNAMIC_BINARY_FIELD_TYPES:

        return True

    if field_name in DYNAMIC_INTERNAL_FIELD_NAMES:

        return True

    if field_name in DYNAMIC_INTERNAL_FIELD_TOKENS:

        return True

    for token in DYNAMIC_SENSITIVE_FIELD_TOKENS:

        if token in field_name:

            return True

    return False


def _dynamic_field_display_score(
    field_name: str,
    field_meta: Dict[str, Any],
) -> float:

    field_name = str(
        field_name or ""
    ).strip()

    field_lower = field_name.lower()

    field_type = str(
        field_meta.get(
            "type",
            field_meta.get(
                "ttype",
                ""
            )
        )
        or ""
    ).lower()

    field_label = str(
        field_meta.get(
            "string",
            field_meta.get(
                "field_description",
                ""
            )
        )
        or ""
    ).lower()

    if _dynamic_field_is_sensitive(
        field_name,
        field_meta,
    ):

        return -1000.0

    score = 0.0

    if field_name == "display_name":

        score += 100.0

    if field_name in {
        "name",
        "description",
        "res_name",
    }:

        score += 90.0

    if field_type == "many2one":

        score += 70.0

    if field_type in {
        "date",
        "datetime",
    }:

        score += 65.0

    if field_type in {
        "integer",
        "float",
        "monetary",
    }:

        score += 45.0

    if field_type == "selection":

        score += 35.0

    if field_type == "boolean":

        score += 25.0

    if field_type in {
        "char",
        "text",
    }:

        score += 20.0

    useful_label_terms = [

        "name",
        "nome",
        "description",
        "descrizione",

        "date",
        "data",

        "type",
        "tipo",

        "file",
        "document",

        "cliente",
        "fornitore",

        "company",
        "azienda",

        "status",
        "stato",

    ]

    for term in useful_label_terms:

        if term in field_label:

            score += 5.0

    technical_terms = [

        "uid",
        "technical",
        "technical_name",

        "internal",
        "resource id",

        "index",
        "hash",

    ]

    for term in technical_terms:

        if term in field_lower:

            score -= 15.0

    return score


def _dynamic_default_fields(
    fields: Dict[str, Dict[str, Any]],
    limit: int = 8,
) -> List[str]:

    if not isinstance(
        fields,
        dict
    ):

        return []

    candidates = []

    for field_name, field_meta in fields.items():

        if not isinstance(
            field_meta,
            dict
        ):

            continue

        score = _dynamic_field_display_score(
            field_name,
            field_meta
        )

        if score <= 0:

            continue

        candidates.append(
            (
                score,
                field_name,
            )
        )

    candidates.sort(
        key=lambda item: (
            -item[0],
            item[1].lower(),
        )
    )

    result = []

    for _score, field_name in candidates:

        if field_name in result:

            continue

        result.append(
            field_name
        )

        if len(result) >= limit:

            break

    return result


def _dynamic_temporal_intent(
    user_message: str,
) -> str:

    text = str(
        user_message or ""
    ).strip().lower()

    if not text:

        return ""

    for phrase in DYNAMIC_MODIFIED_TERMS:

        if phrase in text:

            return "modified"

    for phrase in DYNAMIC_RECENT_TERMS:

        if phrase in text:

            return "created"

    return ""


def _dynamic_choose_date_field(
    fields: Dict[str, Dict[str, Any]],
    user_message: str,
) -> Optional[str]:

    if not isinstance(
        fields,
        dict
    ):

        return None

    intent = _dynamic_temporal_intent(
        user_message
    )

    if not intent:

        return None

    temporal_fields = []

    for field_name, field_meta in fields.items():

        if not isinstance(
            field_meta,
            dict
        ):

            continue

        field_type = str(
            field_meta.get(
                "type",
                field_meta.get(
                    "ttype",
                    ""
                )
            )
            or ""
        ).lower()

        if field_type not in {
            "date",
            "datetime",
        }:

            continue

        if _dynamic_field_is_sensitive(
            field_name,
            field_meta,
        ):

            continue

        field_lower = (
            str(
                field_name
                or ""
            )
            .strip()
            .lower()
        )

        label_lower = str(
            field_meta.get(
                "string",
                field_meta.get(
                    "field_description",
                    ""
                )
            )
            or ""
        ).lower()

        score = 0.0

        if field_lower == "create_date":

            score += 100.0

        if "created" in field_lower:

            score += 25.0

        if "creat" in label_lower:

            score += 20.0

        if "creazione" in label_lower:

            score += 20.0

        if field_lower == "write_date":

            score += 100.0

        if "updated" in label_lower:

            score += 30.0

        if "modified" in label_lower:

            score += 30.0

        if "modifica" in label_lower:

            score += 30.0

        if intent == "created":

            if field_lower == "create_date":

                score += 100.0

            elif field_lower == "write_date":

                score -= 30.0

        elif intent == "modified":

            if field_lower == "write_date":

                score += 100.0

            elif field_lower == "create_date":

                score -= 30.0

        if field_type == "datetime":

            score += 10.0

        if field_type == "date":

            score += 5.0

        temporal_fields.append(
            (
                score,
                field_name,
            )
        )

    if not temporal_fields:

        return None

    temporal_fields.sort(
        key=lambda item: (
            -item[0],
            item[1].lower(),
        )
    )

    return temporal_fields[0][1]


def _dynamic_metadata_text(
    field_meta: Dict[str, Any]
) -> str:

    if not isinstance(
        field_meta,
        dict
    ):

        return ""

    values = [

        field_meta.get(
            "name",
            ""
        ),

        field_meta.get(
            "string",
            field_meta.get(
                "field_description",
                ""
            )
        ),

        field_meta.get(
            "help",
            ""
        ),

        field_meta.get(
            "ttype",
            field_meta.get(
                "type",
                ""
            )
        ),

        field_meta.get(
            "relation",
            ""
        ),

    ]

    parts = []

    for value in values:

        text = str(
            value or ""
        ).strip()

        if text:

            parts.append(
                text
            )

    return " ".join(
        parts
    )


def _dynamic_relation_tokens(
    field_meta: Dict[str, Any]
) -> List[str]:

    relation = str(
        (
            field_meta.get(
                "relation",
                ""
            )
            if isinstance(
                field_meta,
                dict
            )
            else ""
        )
        or ""
    ).strip()

    if not relation:

        return []

    return _normalize_semantic_tokens(
        relation
    )


# ==========================================================
# SEMANTIC FIELD RESOLUTION
# ==========================================================

# Token troppo generici per costituire da soli una prova
# semantica valida durante una sostituzione dinamica.
#
# Non sono mapping di dominio.
#
# Servono solo a impedire trasformazioni arbitrarie tipo:
#
#   name -> display_name
#
# solo perché entrambi sono nomi tecnici generici.
DYNAMIC_GENERIC_SEMANTIC_TOKENS = {

    "id",
    "name",
    "display",
    "value",
    "label",
    "code",

}


def _dynamic_non_generic_tokens(
    tokens: List[str],
) -> List[str]:

    if not isinstance(
        tokens,
        list
    ):

        return []

    return [

        token

        for token in tokens

        if token
        and token not in DYNAMIC_GENERIC_SEMANTIC_TOKENS

    ]


def _dynamic_find_semantic_field(
    fields: Dict[str, Dict[str, Any]],
    source_field: str,
    user_message: str = "",
) -> Optional[str]:

    """
    Risoluzione semantica esclusivamente sui metadata reali
    dell'istanza Odoo.

    Regole:

    1. Un match tecnico esatto è sempre valido.

    2. Un campo candidato semanticamente diverso deve avere
       evidenza reale nei metadata:
         - technical name
         - field label
         - help
         - relation

       oppure evidenza nel contesto della richiesta.

    3. Il tipo del campo, incluso many2one, NON è sufficiente.

    4. Token generici come "name" e "id" NON possono produrre
       da soli una sostituzione semantica.

    5. Un candidato ambiguo viene rifiutato quando il margine
       rispetto al secondo candidato è insufficiente.
    """

    if not isinstance(
        fields,
        dict
    ):

        return None

    source_field = str(
        source_field or ""
    ).strip()

    user_message = str(
        user_message or ""
    ).strip()

    if not source_field:

        return None

    # ======================================================
    # MATCH TECNICO ESATTO
    # ======================================================

    source_lower = (
        source_field.lower()
    )

    for field_name in fields.keys():

        field_name_text = str(
            field_name or ""
        ).strip()

        if (
            field_name_text
            and field_name_text.lower()
            == source_lower
        ):

            field_meta = (
                fields.get(
                    field_name,
                    {}
                )
            )

            print(
                "\n===== SEMANTIC FIELD SEARCH ====="
            )

            print(
                "SOURCE FIELD:",
                source_field
            )

            print(
                "EXACT TECHNICAL MATCH:",
                field_name_text
            )

            if isinstance(
                field_meta,
                dict
            ):

                print(
                    "MATCH TYPE:",
                    field_meta.get(
                        "ttype",
                        field_meta.get(
                            "type",
                            ""
                        )
                    )
                )

                print(
                    "MATCH RELATION:",
                    field_meta.get(
                        "relation"
                    )
                )

                print(
                    "MATCH LABEL:",
                    field_meta.get(
                        "string",
                        field_meta.get(
                            "field_description",
                            ""
                        )
                    )
                )

            return field_name_text

    source_tokens = _normalize_semantic_tokens(
        source_field
    )

    request_tokens = _normalize_semantic_tokens(
        user_message
    )

    if not source_tokens:

        return None

    source_non_generic_tokens = (
        _dynamic_non_generic_tokens(
            source_tokens
        )
    )

    candidates = []

    for field_name, field_meta in fields.items():

        if not isinstance(
            field_meta,
            dict
        ):

            continue

        field_name = str(
            field_name or ""
        ).strip()

        if not field_name:

            continue

        if _dynamic_field_is_sensitive(
            field_name,
            field_meta
        ):

            continue

        field_type = str(
            field_meta.get(
                "type",
                field_meta.get(
                    "ttype",
                    ""
                )
            )
            or ""
        ).lower()

        field_label = str(
            field_meta.get(
                "string",
                field_meta.get(
                    "field_description",
                    ""
                )
            )
            or ""
        )

        field_help = str(
            field_meta.get(
                "help",
                ""
            )
            or ""
        )

        relation_tokens = (
            _dynamic_relation_tokens(
                field_meta
            )
        )

        name_tokens = _normalize_semantic_tokens(
            field_name
        )

        label_tokens = _normalize_semantic_tokens(
            field_label
        )

        help_tokens = _normalize_semantic_tokens(
            field_help
        )

        metadata_tokens = _normalize_semantic_tokens(
            _dynamic_metadata_text(
                field_meta
            )
        )

        name_text = " ".join(
            name_tokens
        )

        label_text = " ".join(
            label_tokens
        )

        help_text = " ".join(
            help_tokens
        )

        relation_text = " ".join(
            relation_tokens
        )

        score = 0.0

        # ==================================================
        # CAMPO PROPOSTO DAL PLANNER
        # ==================================================

        for token in source_tokens:

            if token in name_tokens:

                score += 55.0

            if token in label_tokens:

                score += 35.0

            if token in help_tokens:

                score += 25.0

            if token in relation_tokens:

                score += 60.0

        # ==================================================
        # RICHIESTA UTENTE
        # ==================================================

        for token in request_tokens:

            if token in name_tokens:

                score += 30.0

            if token in label_tokens:

                score += 60.0

            if token in help_tokens:

                score += 35.0

            if token in relation_tokens:

                score += 45.0

            if token in metadata_tokens:

                score += 20.0

        # ==================================================
        # MATCH COMPLETO
        # ==================================================

        source_text = " ".join(
            source_tokens
        )

        if source_text:

            if source_text == name_text:

                score += 150.0

            if source_text == label_text:

                score += 80.0

            if (
                source_text
                and source_text in label_text
            ):

                score += 50.0

            if (
                source_text
                and source_text in help_text
            ):

                score += 35.0

            if (
                source_text
                and source_text in relation_text
            ):

                score += 65.0

        # ==================================================
        # RELATION SEMANTICA
        # ==================================================

        relation_overlap = sum(
            1
            for token in source_non_generic_tokens
            if token in relation_tokens
        )

        if relation_overlap:

            score += (
                90.0
                * relation_overlap
            )

            if field_type == "many2one":

                score += 35.0

        # ==================================================
        # MANY2ONE
        #
        # Segnale tecnico debole.
        # NON vale come evidenza semantica autonoma.
        # ==================================================

        if field_type == "many2one":

            score += 25.0

        # ==================================================
        # STORED
        # ==================================================

        if field_meta.get(
            "store"
        ) is True:

            score += 10.0

        # ==================================================
        # PENALITA'
        # ==================================================

        if field_name in {
            "id",
            "__last_update",
            "create_uid",
            "write_uid",
        }:

            score -= 100.0

        if field_name.endswith(
            "_ids"
        ):

            score -= 5.0

        if any(
            token in {
                "internal",
                "technical",
                "index",
                "hash",
                "checksum",
            }
            for token in name_tokens
        ):

            score -= 20.0

        if score <= 0:

            continue

        # ==================================================
        # EVIDENZA SEMANTICA REALE
        # ==================================================

        source_name_overlap = set(
            source_non_generic_tokens
        ).intersection(
            name_tokens
        )

        source_label_overlap = set(
            source_non_generic_tokens
        ).intersection(
            label_tokens
        )

        source_help_overlap = set(
            source_non_generic_tokens
        ).intersection(
            help_tokens
        )

        source_relation_overlap = set(
            source_non_generic_tokens
        ).intersection(
            relation_tokens
        )

        request_name_overlap = set(
            request_tokens
        ).intersection(
            name_tokens
        )

        request_label_overlap = set(
            request_tokens
        ).intersection(
            label_tokens
        )

        request_help_overlap = set(
            request_tokens
        ).intersection(
            help_tokens
        )

        request_relation_overlap = set(
            request_tokens
        ).intersection(
            relation_tokens
        )

        metadata_evidence = bool(
            source_name_overlap
            or source_label_overlap
            or source_help_overlap
            or source_relation_overlap
        )

        request_evidence = bool(
            request_name_overlap
            or request_label_overlap
            or request_help_overlap
            or request_relation_overlap
        )

        # --------------------------------------------------
        # CASO SOURCE COMPLETAMENTE GENERICO
        #
        # "name", "id", "code", ecc.
        #
        # Non permettere che producano automaticamente:
        #
        #   name -> display_name
        #
        #   id -> qualche altro id
        #
        # senza una prova indipendente.
        # --------------------------------------------------

        if (
            not source_non_generic_tokens
            and not request_evidence
        ):

            continue

        # --------------------------------------------------
        # CASO SOURCE SEMANTICAMENTE INFORMATIVO
        #
        # Se abbiamo un source come:
        #
        #   partner_id
        #   product_id
        #   state
        #
        # deve esistere una reale evidenza metadata/request.
        # --------------------------------------------------

        if (
            source_non_generic_tokens
            and not metadata_evidence
            and not request_evidence
        ):

            continue

        candidates.append(
            {
                "score":
                    score,

                "name":
                    field_name,

                "type":
                    field_type,

                "label":
                    field_label,

                "help":
                    field_help,

                "relation":
                    field_meta.get(
                        "relation"
                    ),

                "name_tokens":
                    name_tokens,

                "label_tokens":
                    label_tokens,

                "help_tokens":
                    help_tokens,

                "relation_tokens":
                    relation_tokens,

                "metadata_tokens":
                    metadata_tokens,

                "source_name_overlap":
                    source_name_overlap,

                "source_label_overlap":
                    source_label_overlap,

                "source_help_overlap":
                    source_help_overlap,

                "source_relation_overlap":
                    source_relation_overlap,

                "request_name_overlap":
                    request_name_overlap,

                "request_label_overlap":
                    request_label_overlap,

                "request_help_overlap":
                    request_help_overlap,

                "request_relation_overlap":
                    request_relation_overlap,

            }
        )

    if not candidates:

        print(
            "\n===== SEMANTIC FIELD REJECTED ====="
        )

        print(
            "SOURCE FIELD:",
            source_field
        )

        print(
            "REASON:",
            "no semantically supported candidates"
        )

        return None

    candidates.sort(
        key=lambda candidate: (
            -candidate["score"],
            candidate["name"].lower(),
        )
    )

    print(
        "\n===== SEMANTIC FIELD SEARCH ====="
    )

    print(
        "SOURCE FIELD:",
        source_field
    )

    print(
        "USER REQUEST:",
        user_message
    )

    print(
        "SOURCE TOKENS:",
        source_tokens
    )

    print(
        "SOURCE NON-GENERIC TOKENS:",
        source_non_generic_tokens
    )

    print(
        "FIELD CANDIDATES:"
    )

    for candidate in candidates[:15]:

        print(
            " -",
            candidate["name"],
            "|",
            candidate["label"],
            "|",
            candidate["type"],
            "| relation:",
            candidate.get(
                "relation"
            ),
            "| score:",
            candidate["score"],
        )

    best = candidates[0]

    best_score = float(
        best.get(
            "score",
            0.0
        )
    )

    second_score = 0.0

    if len(candidates) > 1:

        second_score = float(
            candidates[1].get(
                "score",
                0.0
            )
        )

    best_name = str(
        best.get(
            "name",
            ""
        )
        or ""
    ).lower()

    best_label = str(
        best.get(
            "label",
            ""
        )
        or ""
    ).lower()

    best_help = str(
        best.get(
            "help",
            ""
        )
        or ""
    ).lower()

    source_non_generic_set = set(
        source_non_generic_tokens
    )

    best_name_tokens = set(
        best.get(
            "name_tokens",
            []
        )
        or []
    )

    best_label_tokens = set(
        best.get(
            "label_tokens",
            []
        )
        or []
    )

    best_help_tokens = set(
        best.get(
            "help_tokens",
            []
        )
        or []
    )

    best_relation_tokens = set(
        best.get(
            "relation_tokens",
            []
        )
        or []
    )

    source_name_overlap = (
        source_non_generic_set
        .intersection(
            best_name_tokens
        )
    )

    source_label_overlap = (
        source_non_generic_set
        .intersection(
            best_label_tokens
        )
    )

    source_help_overlap = (
        source_non_generic_set
        .intersection(
            best_help_tokens
        )
    )

    source_relation_overlap = (
        source_non_generic_set
        .intersection(
            best_relation_tokens
        )
    )

    request_name_overlap = (
        set(request_tokens)
        .intersection(
            best_name_tokens
        )
    )

    request_label_overlap = (
        set(request_tokens)
        .intersection(
            best_label_tokens
        )
    )

    request_help_overlap = (
        set(request_tokens)
        .intersection(
            best_help_tokens
        )
    )

    request_relation_overlap = (
        set(request_tokens)
        .intersection(
            best_relation_tokens
        )
    )

    metadata_evidence = bool(
        source_name_overlap
        or source_label_overlap
        or source_help_overlap
        or source_relation_overlap
    )

    request_evidence = bool(
        request_name_overlap
        or request_label_overlap
        or request_help_overlap
        or request_relation_overlap
    )

    generic_source_only = (
        not source_non_generic_tokens
    )

    minimum_score = 80.0

    margin_required = 15.0

    if (
        generic_source_only
        and not request_evidence
    ):

        print(
            "\n===== SEMANTIC FIELD REJECTED ====="
        )

        print(
            "SOURCE FIELD:",
            source_field
        )

        print(
            "BEST CANDIDATE:",
            best["name"]
        )

        print(
            "BEST SCORE:",
            best_score
        )

        print(
            "REASON:",
            "generic source field lacks independent semantic evidence"
        )

        return None

    if (
        not generic_source_only
        and not metadata_evidence
        and not request_evidence
    ):

        print(
            "\n===== SEMANTIC FIELD REJECTED ====="
        )

        print(
            "SOURCE FIELD:",
            source_field
        )

        print(
            "BEST CANDIDATE:",
            best["name"]
        )

        print(
            "BEST SCORE:",
            best_score
        )

        print(
            "REASON:",
            "no direct metadata or request evidence"
        )

        return None

    if best_score < minimum_score:

        print(
            "\n===== SEMANTIC FIELD REJECTED ====="
        )

        print(
            "SOURCE FIELD:",
            source_field
        )

        print(
            "BEST CANDIDATE:",
            best["name"]
        )

        print(
            "BEST SCORE:",
            best_score
        )

        print(
            "REASON:",
            "score below semantic threshold"
        )

        return None

    strong_direct_match = bool(
        source_name_overlap
        or source_label_overlap
        or source_help_overlap
        or source_relation_overlap
        or request_name_overlap
        or request_label_overlap
        or request_help_overlap
        or request_relation_overlap
    )

    if (
        len(candidates) > 1
        and not strong_direct_match
    ):

        margin = (
            best_score
            - second_score
        )

        if margin < margin_required:

            print(
                "\n===== SEMANTIC FIELD REJECTED ====="
            )

            print(
                "SOURCE FIELD:",
                source_field
            )

            print(
                "BEST CANDIDATE:",
                best["name"]
            )

            print(
                "BEST SCORE:",
                best_score
            )

            print(
                "SECOND SCORE:",
                second_score
            )

            print(
                "MARGIN:",
                margin
            )

            print(
                "REASON:",
                "ambiguous semantic resolution"
            )

            return None

    print(
        "\n===== SEMANTIC FIELD ACCEPTED ====="
    )

    print(
        "SOURCE FIELD:",
        source_field
    )

    print(
        "SELECTED FIELD:",
        best["name"]
    )

    print(
        "SELECTED TYPE:",
        best["type"]
    )

    print(
        "SELECTED RELATION:",
        best.get(
            "relation"
        )
    )

    print(
        "SELECTED LABEL:",
        best.get(
            "label"
        )
    )

    print(
        "SCORE:",
        best_score
    )

    print(
        "SOURCE EVIDENCE:",
        {
            "name":
                sorted(source_name_overlap),

            "label":
                sorted(source_label_overlap),

            "help":
                sorted(source_help_overlap),

            "relation":
                sorted(source_relation_overlap),

        }
    )

    print(
        "REQUEST EVIDENCE:",
        {
            "name":
                sorted(request_name_overlap),

            "label":
                sorted(request_label_overlap),

            "help":
                sorted(request_help_overlap),

            "relation":
                sorted(request_relation_overlap),

        }
    )

    return best["name"]


def _dynamic_resolve_field_expression(
    expression: Any,
    fields: Dict[str, Dict[str, Any]],
    user_message: str = "",
) -> Optional[str]:

    if not isinstance(
        expression,
        str
    ):

        return None

    expression = expression.strip()

    if not expression:

        return None

    if expression == "__count":

        return "__count"

    aggregate = None
    base_expression = expression

    if ":" in expression:

        possible_base, possible_aggregate = (
            expression.split(
                ":",
                1
            )
        )

        possible_base = (
            possible_base.strip()
        )

        possible_aggregate = (
            possible_aggregate
            .strip()
            .lower()
        )

        if possible_aggregate in {
            "sum",
            "avg",
            "min",
            "max",
            "count",
            "count_distinct",
        }:

            base_expression = (
                possible_base
            )

            aggregate = (
                possible_aggregate
            )

    suffix = None

    if ":" in base_expression:

        root_candidate, root_suffix = (
            base_expression.split(
                ":",
                1
            )
        )

        if (
            root_candidate
            and root_suffix
        ):

            base_expression = (
                root_candidate.strip()
            )

            suffix = (
                root_suffix.strip()
            )

    if base_expression in fields:

        resolved_base = (
            base_expression
        )

    else:

        resolved_base = (
            _dynamic_find_semantic_field(
                fields=fields,
                source_field=base_expression,
                user_message=user_message,
            )
        )

        if not resolved_base:

            return None

    resolved = (
        resolved_base
    )

    if suffix:

        resolved = (
            f"{resolved}:{suffix}"
        )

    if aggregate:

        resolved = (
            f"{resolved}:{aggregate}"
        )

    return resolved


def _dynamic_resolve_field_list(
    values: Any,
    fields: Dict[str, Dict[str, Any]],
    user_message: str = "",
) -> List[Any]:

    if not isinstance(
        values,
        list
    ):

        return []

    result = []

    for value in values:

        if not isinstance(
            value,
            str
        ):

            continue

        value = value.strip()

        if not value:

            continue

        if value == "__count":

            result.append(
                value
            )

            continue

        resolved = (
            _dynamic_resolve_field_expression(
                expression=value,
                fields=fields,
                user_message=user_message,
            )
        )

        if resolved:

            result.append(
                resolved
            )

        else:

            print(
                "\n===== DYNAMIC FIELD UNRESOLVED ====="
            )

            print(
                "REQUESTED:",
                value
            )

    return result


def _dynamic_resolve_groupby(
    values: Any,
    fields: Dict[str, Dict[str, Any]],
    user_message: str = "",
) -> List[Any]:

    if not isinstance(
        values,
        list
    ):

        return []

    result = []

    for value in values:

        if not isinstance(
            value,
            str
        ):

            continue

        value = value.strip()

        if not value:

            continue

        resolved = (
            _dynamic_resolve_field_expression(
                expression=value,
                fields=fields,
                user_message=user_message,
            )
        )

        if resolved:

            result.append(
                resolved
            )

    return result


def _dynamic_resolve_orderby(
    orderby: Any,
    fields: Dict[str, Dict[str, Any]],
    user_message: str = "",
) -> Optional[str]:

    if not isinstance(
        orderby,
        str
    ):

        return orderby

    text = orderby.strip()

    if not text:

        return orderby

    parts = text.split()

    field_expression = parts[0]

    direction = (
        parts[1].lower()
        if len(parts) > 1
        else "asc"
    )

    if direction not in {
        "asc",
        "desc",
    }:

        direction = "asc"

    if field_expression == "__count":

        return (
            f"__count {direction}"
        )

    resolved_field = (
        _dynamic_resolve_field_expression(
            expression=field_expression,
            fields=fields,
            user_message=user_message,
        )
    )

    if not resolved_field:

        print(
            "\n===== DYNAMIC ORDERBY UNRESOLVED ====="
        )

        print(
            "REQUESTED:",
            field_expression
        )

        return None

    return (
        f"{resolved_field} {direction}"
    )


def _dynamic_apply_parameter_field_resolution(
    params: Dict[str, Any],
    fields: Dict[str, Dict[str, Any]],
    user_message: str = "",
) -> Dict[str, Any]:

    if not isinstance(
        params,
        dict
    ):

        return {}

    if not isinstance(
        fields,
        dict
    ):

        return params

    original_groupby = params.get(
        "groupby"
    )

    if isinstance(
        original_groupby,
        str
    ):

        normalized_groupby = [
            original_groupby.strip()
        ]

        normalized_groupby = [
            value
            for value in normalized_groupby
            if value
        ]

        params["groupby"] = (
            normalized_groupby
        )

        print(
            "\n===== GROUPBY TYPE NORMALIZATION ====="
        )

        print(
            "ORIGINAL:",
            original_groupby
        )

        print(
            "NORMALIZED:",
            normalized_groupby
        )

    elif (
        original_groupby is not None
        and not isinstance(
            original_groupby,
            list
        )
    ):

        params["groupby"] = []

    original_fields = params.get(
        "fields"
    )

    if isinstance(
        original_fields,
        list
    ) and original_fields:

        resolved_fields = (
            _dynamic_resolve_field_list(
                values=original_fields,
                fields=fields,
                user_message=user_message,
            )
        )

        if resolved_fields:

            if resolved_fields != original_fields:

                print(
                    "\n===== DYNAMIC FIELDS RESOLUTION ====="
                )

                print(
                    "ORIGINAL:",
                    original_fields
                )

                print(
                    "RESOLVED:",
                    resolved_fields
                )

            params["fields"] = (
                resolved_fields
            )

    elif isinstance(
        original_fields,
        str
    ):

        resolved_fields = (
            _dynamic_resolve_field_list(
                values=[
                    original_fields
                ],
                fields=fields,
                user_message=user_message,
            )
        )

        params["fields"] = (
            resolved_fields
        )

    groupby_values = params.get(
        "groupby"
    )

    if isinstance(
        groupby_values,
        list
    ) and groupby_values:

        resolved_groupby = (
            _dynamic_resolve_groupby(
                values=groupby_values,
                fields=fields,
                user_message=user_message,
            )
        )

        if resolved_groupby:

            if resolved_groupby != groupby_values:

                print(
                    "\n===== DYNAMIC GROUPBY RESOLUTION ====="
                )

                print(
                    "ORIGINAL:",
                    groupby_values
                )

                print(
                    "RESOLVED:",
                    resolved_groupby
                )

            params["groupby"] = (
                resolved_groupby
            )

        else:

            params["groupby"] = []

    original_orderby = params.get(
        "orderby"
    )

    resolved_orderby = (
        _dynamic_resolve_orderby(
            orderby=original_orderby,
            fields=fields,
            user_message=user_message,
        )
    )

    if (
        resolved_orderby
        and resolved_orderby != original_orderby
    ):

        print(
            "\n===== DYNAMIC ORDERBY RESOLUTION ====="
        )

        print(
            "ORIGINAL:",
            original_orderby
        )

        print(
            "RESOLVED:",
            resolved_orderby
        )

        params["orderby"] = (
            resolved_orderby
        )

    return params


def _dynamic_apply_field_resolution(
    params: Dict[str, Any],
    fields: Dict[str, Dict[str, Any]],
    user_message: str,
) -> Dict[str, Any]:

    if not isinstance(
        params,
        dict
    ):

        params = {}

    if not isinstance(
        fields,
        dict
    ):

        fields = {}

    requested_fields = params.get(
        "fields"
    )

    if (
        not isinstance(
            requested_fields,
            list
        )
        or not requested_fields
    ):

        dynamic_fields = (
            _dynamic_default_fields(
                fields=fields,
                limit=8,
            )
        )

        if dynamic_fields:

            params["fields"] = (
                dynamic_fields
            )

            print(
                "\n===== DYNAMIC FIELD RESOLUTION ====="
            )

            print(
                "AUTO FIELDS:",
                dynamic_fields
            )

    params = (
        _dynamic_apply_parameter_field_resolution(
            params=params,
            fields=fields,
            user_message=user_message,
        )
    )

    date_field = (
        _dynamic_choose_date_field(
            fields=fields,
            user_message=user_message,
        )
    )

    if date_field:

        print(
            "\n===== DYNAMIC DATE FIELD ====="
        )

        print(
            "SELECTED:",
            date_field
        )

    current_order = params.get(
        "order"
    )

    current_order = (
        str(
            current_order or ""
        )
        .strip()
    )

    temporal_intent = (
        _dynamic_temporal_intent(
            user_message
        )
    )

    if (
        date_field
        and temporal_intent
        and (
            not current_order
            or current_order.lower()
            in {
                "id desc",
                "id asc",
            }
        )
    ):

        params["order"] = (
            f"{date_field} desc"
        )

        print(
            "\n===== DYNAMIC ORDER ====="
        )

        print(
            "ORDER:",
            params["order"]
        )

    return params


def _dynamic_remove_invalid_fields(
    params: Dict[str, Any],
    fields: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:

    if not isinstance(
        params,
        dict
    ):

        return {}

    if not isinstance(
        fields,
        dict
    ) or not fields:

        return params

    requested_fields = params.get(
        "fields"
    )

    if isinstance(
        requested_fields,
        list
    ):

        valid_fields = []

        for field_expression in requested_fields:

            if not isinstance(
                field_expression,
                str
            ):

                continue

            resolved = (
                _dynamic_resolve_field_expression(
                    expression=field_expression,
                    fields=fields,
                    user_message="",
                )
            )

            if resolved:

                valid_fields.append(
                    resolved
                )

        params["fields"] = (
            valid_fields
        )

    requested_groupby = params.get(
        "groupby"
    )

    if isinstance(
        requested_groupby,
        list
    ):

        valid_groupby = []

        for group_expression in requested_groupby:

            if not isinstance(
                group_expression,
                str
            ):

                continue

            resolved = (
                _dynamic_resolve_field_expression(
                    expression=group_expression,
                    fields=fields,
                    user_message="",
                )
            )

            if resolved:

                valid_groupby.append(
                    resolved
                )

        params["groupby"] = (
            valid_groupby
        )

    return params


# ==========================================================
# DYNAMIC DOMAIN RESOLUTION
# ==========================================================

def _normalize_semantic_tokens(
    value: Any
) -> List[str]:

    text = str(
        value or ""
    ).strip().lower()

    if not text:

        return []

    text = text.replace(
        "_",
        " "
    )

    text = re.sub(
        r"[^a-z0-9àèéìòù\s]+",
        " ",
        text
    )

    return [
        token
        for token in text.split()
        if token
    ]


def _dynamic_translate_domain_condition(
    condition: List[Any],
    fields: Dict[str, Dict[str, Any]],
    user_message: str = "",
) -> Optional[List[Any]]:

    if not isinstance(
        condition,
        list
    ):

        return condition

    if len(condition) != 3:

        return condition

    field = condition[0]
    operator = condition[1]
    value = condition[2]

    if not isinstance(
        field,
        str
    ):

        return condition

    if not isinstance(
        operator,
        str
    ):

        return condition

    field = field.strip()

    root_field = field.split(
        ".",
        1
    )[0]

    if root_field in fields:

        return condition

    replacement = (
        _dynamic_find_semantic_field(
            fields=fields,
            source_field=root_field,
            user_message=user_message,
        )
    )

    if not replacement:

        return None

    replacement_meta = (
        fields.get(
            replacement,
            {}
        )
    )

    replacement_type = str(
        replacement_meta.get(
            "type",
            replacement_meta.get(
                "ttype",
                ""
            )
        )
        or ""
    ).lower()

    field_lower = field.lower()

    if (
        "rank" in field_lower
        and replacement_type == "boolean"
    ):

        numeric_operators = {
            ">",
            ">=",
            "!=",
            "<",
            "<=",
            "=",
        }

        if operator in numeric_operators:

            try:

                numeric_value = float(
                    value
                )

            except (
                TypeError,
                ValueError
            ):

                numeric_value = None

            if numeric_value is not None:

                if operator in {
                    ">",
                    ">=",
                } and numeric_value >= 0:

                    return [
                        replacement,
                        "=",
                        True,
                    ]

                if operator == "=":

                    return [
                        replacement,
                        "=",
                        bool(
                            numeric_value
                        ),
                    ]

                if operator == "!=":

                    return [
                        replacement,
                        "!=",
                        bool(
                            numeric_value
                        ),
                    ]

    nested_tail = None

    if "." in field:

        _root, nested_tail = (
            field.split(
                ".",
                1
            )
        )

    if nested_tail:

        return [
            replacement,
            operator,
            value,
        ]

    return [
        replacement,
        operator,
        value,
    ]


def _dynamic_repair_domain(
    params: Dict[str, Any],
    fields: Dict[str, Dict[str, Any]],
    user_message: str = "",
) -> Dict[str, Any]:

    if not isinstance(
        params,
        dict
    ):

        return {}

    if not isinstance(
        fields,
        dict
    ) or not fields:

        return params

    domain = params.get(
        "domain"
    )

    if not isinstance(
        domain,
        list
    ):

        return params

    repaired = []

    for condition in domain:

        if isinstance(
            condition,
            str
        ):

            if condition in {
                "&",
                "|",
                "!",
            }:

                repaired.append(
                    condition
                )

            continue

        if not isinstance(
            condition,
            list
        ):

            continue

        translated = (
            _dynamic_translate_domain_condition(
                condition=condition,
                fields=fields,
                user_message=user_message,
            )
        )

        if translated is None:

            print(
                "\n===== DYNAMIC DOMAIN FIELD REMOVED ====="
            )

            print(
                "INVALID CONDITION:",
                condition
            )

            continue

        if translated != condition:

            print(
                "\n===== DYNAMIC DOMAIN FIELD RESOLUTION ====="
            )

            print(
                "ORIGINAL:",
                condition
            )

            print(
                "RESOLVED:",
                translated
            )

        repaired.append(
            translated
        )

    params["domain"] = repaired

    return params


# ==========================================================
# METADATA VALIDATION HELPERS
# ==========================================================

def _dynamic_expression_base(
    expression: Any
) -> Optional[str]:

    if not isinstance(
        expression,
        str
    ):

        return None

    text = expression.strip()

    if not text:

        return None

    if text == "__count":

        return "__count"

    if ":" in text:

        first, suffix = (
            text.split(
                ":",
                1
            )
        )

        if suffix.strip().lower() in {
            "sum",
            "avg",
            "min",
            "max",
            "count",
            "count_distinct",
            "month",
            "week",
            "day",
            "quarter",
            "year",
        }:

            return first.strip()

    return text


def _dynamic_reapply_resolved_parameter_fields(
    parameters: Dict[str, Any],
    source_params: Dict[str, Any],
) -> Dict[str, Any]:

    if not isinstance(
        parameters,
        dict
    ):

        return parameters

    params = parameters.get(
        "params"
    )

    if not isinstance(
        params,
        dict
    ):

        params = {}

    if not isinstance(
        source_params,
        dict
    ):

        source_params = {}

    source_fields = source_params.get(
        "fields"
    )

    current_fields = params.get(
        "fields"
    )

    if (
        isinstance(
            source_fields,
            list
        )
        and source_fields
    ):

        if not isinstance(
            current_fields,
            list
        ) or not current_fields:

            params["fields"] = (
                list(
                    source_fields
                )
            )

    source_groupby = source_params.get(
        "groupby"
    )

    current_groupby = params.get(
        "groupby"
    )

    if (
        isinstance(
            source_groupby,
            list
        )
        and source_groupby
    ):

        if not isinstance(
            current_groupby,
            list
        ) or not current_groupby:

            params["groupby"] = (
                list(
                    source_groupby
                )
            )

    source_orderby = source_params.get(
        "orderby"
    )

    if source_orderby:

        current_orderby = params.get(
            "orderby"
        )

        if not current_orderby:

            params["orderby"] = (
                source_orderby
            )

    parameters["params"] = params

    return parameters


# ==========================================================
# DYNAMIC MODEL FALLBACK
# ==========================================================

def _dynamic_parameter_root_fields(
    params: Dict[str, Any]
) -> List[str]:

    if not isinstance(
        params,
        dict
    ):

        return []

    expressions: List[str] = []

    groupby = params.get(
        "groupby"
    )

    if isinstance(
        groupby,
        str
    ):

        groupby = [
            groupby
        ]

    if isinstance(
        groupby,
        list
    ):

        expressions.extend(
            groupby
        )

    fields = params.get(
        "fields"
    )

    if isinstance(
        fields,
        str
    ):

        fields = [
            fields
        ]

    if isinstance(
        fields,
        list
    ):

        expressions.extend(
            fields
        )

    result: List[str] = []

    for expression in expressions:

        if not isinstance(
            expression,
            str
        ):

            continue

        expression = expression.strip()

        if not expression:

            continue

        if expression == "__count":

            continue

        root = _dynamic_expression_base(
            expression
        )

        if not root:

            continue

        if root == "__count":

            continue

        if root not in result:

            result.append(
                root
            )

    return result


def _dynamic_model_context_text(
    model: str,
    metadata: Dict[str, Any]
) -> str:

    values = [
        model
    ]

    if isinstance(
        metadata,
        dict
    ):

        values.extend(
            [

                metadata.get(
                    "name",
                    ""
                ),

                metadata.get(
                    "string",
                    ""
                ),

                metadata.get(
                    "model_description",
                    ""
                ),

                metadata.get(
                    "description",
                    ""
                ),

                metadata.get(
                    "help",
                    ""
                ),

            ]
        )

    return " ".join(
        str(
            value or ""
        )
        for value in values
    )


def _dynamic_model_candidate_score(
    model: str,
    metadata: Dict[str, Any],
    user_message: str,
    current_model: str = "",
    current_metadata: Optional[Dict[str, Any]] = None,
) -> float:

    candidate_text = _dynamic_model_context_text(
        model=model,
        metadata=metadata,
    )

    request_tokens = set(
        _normalize_semantic_tokens(
            user_message
        )
    )

    candidate_tokens = set(
        _normalize_semantic_tokens(
            candidate_text
        )
    )

    score = 0.0

    request_overlap = (
        request_tokens
        .intersection(
            candidate_tokens
        )
    )

    score += (
        len(
            request_overlap
        )
        * 10.0
    )

    if current_model:

        current_text = _dynamic_model_context_text(
            model=current_model,
            metadata=current_metadata or {},
        )

        current_tokens = set(
            _normalize_semantic_tokens(
                current_text
            )
        )

        current_overlap = (
            current_tokens
            .intersection(
                candidate_tokens
            )
        )

        score += (
            len(
                current_overlap
            )
            * 6.0
        )

    model_text = str(
        model or ""
    ).lower()

    technical_penalties = {

        "report": -8.0,

        "wizard": -12.0,

        "transient": -10.0,

        "line": -2.0,

    }

    for token, penalty in technical_penalties.items():

        if token in model_text:

            score += penalty

    return score


def _dynamic_extract_model_records(
    response: Any
) -> List[Dict[str, Any]]:

    if not isinstance(
        response,
        dict
    ):

        return []

    payload = response.get(
        "result"
    )

    if isinstance(
        payload,
        list
    ):

        return [

            row

            for row in payload

            if isinstance(
                row,
                dict
            )

        ]

    if isinstance(
        payload,
        dict
    ):

        data = payload.get(
            "data"
        )

        if isinstance(
            data,
            list
        ):

            return [

                row

                for row in data

                if isinstance(
                    row,
                    dict
                )

            ]

    data = response.get(
        "data"
    )

    if isinstance(
        data,
        list
    ):

        return [

            row

            for row in data

            if isinstance(
                row,
                dict
            )

        ]

    return []


def _dynamic_extract_field_records(
    response: Any
) -> List[Dict[str, Any]]:

    return _dynamic_extract_model_records(
        response
    )


def _dynamic_required_fields_compatible(
    params: Dict[str, Any],
    fields: Dict[str, Dict[str, Any]],
    user_message: str,
) -> Tuple[
    bool,
    Dict[str, str]
]:

    required_fields = (
        _dynamic_parameter_root_fields(
            params
        )
    )

    if not required_fields:

        return (
            True,
            {}
        )

    if not isinstance(
        fields,
        dict
    ) or not fields:

        return (
            False,
            {}
        )

    resolved_fields: Dict[str, str] = {}

    print(
        "\n===== DYNAMIC MODEL REQUIRED-FIELD COMPATIBILITY ====="
    )

    print(
        "REQUIRED FIELDS:",
        required_fields
    )

    for source_field in required_fields:

        source_field = str(
            source_field or ""
        ).strip()

        if not source_field:

            continue

        # ==================================================
        # EXACT TECHNICAL FIELD
        #
        # Se il campo tecnico esiste realmente nel modello,
        # il metadata Odoo costituisce una prova forte.
        # ==================================================

        if source_field in fields:

            resolved_fields[
                source_field
            ] = source_field

            exact_meta = fields.get(
                source_field,
                {}
            )

            print(
                "FIELD COMPATIBLE:",
                source_field,
                "->",
                source_field,
                "| exact technical match"
            )

            if isinstance(
                exact_meta,
                dict
            ):

                print(
                    "  LABEL:",
                    exact_meta.get(
                        "string",
                        exact_meta.get(
                            "field_description",
                            ""
                        )
                    )
                )

                print(
                    "  TYPE:",
                    exact_meta.get(
                        "ttype",
                        exact_meta.get(
                            "type",
                            ""
                        )
                    )
                )

                print(
                    "  RELATION:",
                    exact_meta.get(
                        "relation"
                    )
                )

            continue

        # ==================================================
        # SEMANTIC RESOLUTION
        # ==================================================

        resolved = (
            _dynamic_find_semantic_field(
                fields=fields,
                source_field=source_field,
                user_message=user_message,
            )
        )

        if not resolved:

            print(
                "\n===== DYNAMIC MODEL COMPATIBILITY FAILED ====="
            )

            print(
                "REQUIRED FIELD:",
                source_field
            )

            print(
                "REASON:",
                "field cannot be semantically resolved with sufficient evidence"
            )

            return (
                False,
                {}
            )

        resolved_meta = fields.get(
            resolved
        )

        if not isinstance(
            resolved_meta,
            dict
        ):

            print(
                "\n===== DYNAMIC MODEL COMPATIBILITY FAILED ====="
            )

            print(
                "REQUIRED FIELD:",
                source_field
            )

            print(
                "RESOLVED FIELD:",
                resolved
            )

            print(
                "REASON:",
                "resolved field metadata unavailable"
            )

            return (
                False,
                {}
            )

        source_tokens = _normalize_semantic_tokens(
            source_field
        )

        source_non_generic_tokens = (
            _dynamic_non_generic_tokens(
                source_tokens
            )
        )

        resolved_name_tokens = _normalize_semantic_tokens(
            resolved
        )

        resolved_label_tokens = _normalize_semantic_tokens(
            resolved_meta.get(
                "string",
                resolved_meta.get(
                    "field_description",
                    ""
                )
            )
        )

        resolved_help_tokens = _normalize_semantic_tokens(
            resolved_meta.get(
                "help",
                ""
            )
        )

        resolved_relation_tokens = _normalize_semantic_tokens(
            resolved_meta.get(
                "relation",
                ""
            )
        )

        source_set = set(
            source_non_generic_tokens
        )

        metadata_evidence = (
            source_set.intersection(
                set(resolved_name_tokens)
            )
            or source_set.intersection(
                set(resolved_label_tokens)
            )
            or source_set.intersection(
                set(resolved_help_tokens)
            )
            or source_set.intersection(
                set(resolved_relation_tokens)
            )
        )

        request_tokens = set(
            _normalize_semantic_tokens(
                user_message
            )
        )

        request_evidence = (
            request_tokens.intersection(
                set(resolved_name_tokens)
            )
            or request_tokens.intersection(
                set(resolved_label_tokens)
            )
            or request_tokens.intersection(
                set(resolved_help_tokens)
            )
            or request_tokens.intersection(
                set(resolved_relation_tokens)
            )
        )

        # ==================================================
        # SECOND SEMANTIC GATE
        # ==================================================

        if (
            not source_non_generic_tokens
            and not metadata_evidence
            and not request_evidence
        ):

            print(
                "\n===== DYNAMIC MODEL COMPATIBILITY FAILED ====="
            )

            print(
                "REQUIRED FIELD:",
                source_field
            )

            print(
                "RESOLVED FIELD:",
                resolved
            )

            print(
                "REASON:",
                "generic source field resolved without semantic evidence"
            )

            return (
                False,
                {}
            )

        if (
            source_non_generic_tokens
            and not metadata_evidence
            and not request_evidence
        ):

            print(
                "\n===== DYNAMIC MODEL COMPATIBILITY FAILED ====="
            )

            print(
                "REQUIRED FIELD:",
                source_field
            )

            print(
                "RESOLVED FIELD:",
                resolved
            )

            print(
                "REASON:",
                "semantic resolution lacks independent metadata/request evidence"
            )

            return (
                False,
                {}
            )

        resolved_fields[
            source_field
        ] = resolved

        print(
            "FIELD COMPATIBLE:",
            source_field,
            "->",
            resolved,
            "| metadata evidence:",
            bool(metadata_evidence),
            "| request evidence:",
            bool(request_evidence),
        )

    # ======================================================
    # COMPLETE COVERAGE CHECK
    #
    # Nessun candidato può essere considerato compatibile se
    # anche un solo campo richiesto rimane irrisolto.
    # ======================================================

    missing_fields = [

        field

        for field in required_fields

        if field not in resolved_fields

    ]

    if missing_fields:

        print(
            "\n===== DYNAMIC MODEL COMPATIBILITY FAILED ====="
        )

        print(
            "MISSING REQUIRED FIELDS:",
            missing_fields
        )

        return (
            False,
            {}
        )

    print(
        "\n===== DYNAMIC MODEL COMPATIBILITY PASSED ====="
    )

    print(
        "REQUIRED FIELDS:",
        required_fields
    )

    print(
        "RESOLVED REQUIRED FIELDS:",
        resolved_fields
    )

    return (
        True,
        resolved_fields
    )


async def _dynamic_find_compatible_model(
    odoo_client,
    metadata_service,
    current_model: str,
    current_metadata: Dict[str, Any],
    current_fields: Dict[str, Dict[str, Any]],
    params: Dict[str, Any],
    user_message: str,
) -> Optional[
    Tuple[
        str,
        Dict[str, Dict[str, Any]],
        Dict[str, Any]
    ]
]:

    required_fields = (
        _dynamic_parameter_root_fields(
            params
        )
    )

    if not required_fields:

        return None

    print(
        "\n============================================"
    )

    print(
        "===== DYNAMIC MODEL FALLBACK ====="
    )

    print(
        "CURRENT MODEL:",
        current_model
    )

    print(
        "REQUIRED FIELDS / CONCEPTS:",
        required_fields
    )

    try:

        model_response = await (
            odoo_client.call_kw(
                model="ir.model",
                method="search_read",
                args=[
                    [
                        [
                            "model",
                            "!=",
                            current_model,
                        ]
                    ]
                ],
                kwargs={
                    "fields": [
                        "id",
                        "model",
                        "name",
                        "state",
                    ],
                    "limit": 0,
                    "order": "model asc",
                },
            )
        )

    except Exception as exc:

        print(
            "\n===== DYNAMIC MODEL FALLBACK ERROR ====="
        )

        print(
            "STEP:",
            "ir.model"
        )

        print(
            "TYPE:",
            type(exc).__name__
        )

        print(
            "MESSAGE:",
            str(exc)
        )

        return None

    model_records = (
        _dynamic_extract_model_records(
            model_response
        )
    )

    if not model_records:

        print(
            "NO MODEL RECORDS FOUND"
        )

        return None

    model_candidates = []

    for record in model_records:

        candidate_model = str(
            record.get(
                "model",
                ""
            )
            or ""
        ).strip()

        if not candidate_model:

            continue

        candidate_score = (
            _dynamic_model_candidate_score(
                model=candidate_model,
                metadata=record,
                user_message=user_message,
                current_model=current_model,
                current_metadata=current_metadata,
            )
        )

        model_candidates.append(
            (
                candidate_score,
                candidate_model,
                record,
            )
        )

    model_candidates.sort(
        key=lambda item: (
            -item[0],
            item[1].lower(),
        )
    )

    # ======================================================
    # IMPORTANTE:
    #
    # NON limitiamo più arbitrariamente ai primi 40 modelli.
    #
    # Il punteggio è solo un ordinamento dei candidati.
    # La compatibilità reale viene determinata soltanto
    # dopo la lettura dei metadata ir.model.fields.
    # ======================================================

    print(
        "\n===== DYNAMIC MODEL CANDIDATE VERIFICATION ====="
    )

    print(
        "TOTAL MODEL CANDIDATES:",
        len(model_candidates)
    )

    print(
        "VERIFYING ALL CANDIDATES AGAINST ir.model.fields"
    )

    print(
        "\n===== DYNAMIC MODEL CANDIDATES ====="
    )

    for score, candidate_model, record in (
        model_candidates[:30]
    ):

        print(
            " -",
            candidate_model,
            "|",
            record.get(
                "name",
                ""
            ),
            "| score:",
            score
        )

    candidate_model_names = [
        candidate_model
        for _score, candidate_model, _record
        in model_candidates
    ]

    if not candidate_model_names:

        return None

    try:

        field_response = await (
            odoo_client.call_kw(
                model="ir.model.fields",
                method="search_read",
                args=[
                    [
                        [
                            "model",
                            "in",
                            candidate_model_names,
                        ]
                    ]
                ],
                kwargs={
                    "fields": [
                        "id",
                        "name",
                        "field_description",
                        "help",
                        "ttype",
                        "relation",
                        "required",
                        "readonly",
                        "store",
                        "index",
                        "model",
                    ],
                    "limit": 0,
                    "order": "model asc, name asc",
                },
            )
        )

    except Exception as exc:

        print(
            "\n===== DYNAMIC MODEL FALLBACK ERROR ====="
        )

        print(
            "STEP:",
            "ir.model.fields"
        )

        print(
            "TYPE:",
            type(exc).__name__
        )

        print(
            "MESSAGE:",
            str(exc)
        )

        return None

    field_records = (
        _dynamic_extract_field_records(
            field_response
        )
    )

    fields_by_model: Dict[
        str,
        Dict[str, Dict[str, Any]]
    ] = {}

    for record in field_records:

        candidate_model = str(
            record.get(
                "model",
                ""
            )
            or ""
        ).strip()

        field_name = str(
            record.get(
                "name",
                ""
            )
            or ""
        ).strip()

        if (
            not candidate_model
            or not field_name
        ):

            continue

        if candidate_model not in fields_by_model:

            fields_by_model[
                candidate_model
            ] = {}

        fields_by_model[
            candidate_model
        ][
            field_name
        ] = {

            "name":
                field_name,

            "string":
                record.get(
                    "field_description",
                    ""
                ),

            "field_description":
                record.get(
                    "field_description",
                    ""
                ),

            "help":
                record.get(
                    "help",
                    ""
                ),

            "ttype":
                record.get(
                    "ttype",
                    ""
                ),

            "type":
                record.get(
                    "ttype",
                    ""
                ),

            "relation":
                record.get(
                    "relation"
                ),

            "required":
                record.get(
                    "required"
                ),

            "readonly":
                record.get(
                    "readonly"
                ),

            "store":
                record.get(
                    "store"
                ),

            "index":
                record.get(
                    "index"
                ),

        }

    compatible_candidates = []

    for (
        model_score,
        candidate_model,
        model_record,
    ) in model_candidates:

        candidate_fields = (
            fields_by_model.get(
                candidate_model,
                {}
            )
        )

        if not candidate_fields:

            print(
                "\n===== DYNAMIC MODEL REJECTED ====="
            )

            print(
                "MODEL:",
                candidate_model
            )

            print(
                "MODEL SCORE:",
                model_score
            )

            print(
                "REASON:",
                "no real ir.model.fields metadata"
            )

            continue

        print(
            "\n----- CHECKING MODEL -----"
        )

        print(
            "MODEL:",
            candidate_model
        )

        print(
            "MODEL SCORE:",
            model_score
        )

        print(
            "FIELD COUNT:",
            len(candidate_fields)
        )

        compatibility = (
            _dynamic_required_fields_compatible(
                params=params,
                fields=candidate_fields,
                user_message=user_message,
            )
        )

        is_compatible = compatibility[
            0
        ]

        resolved_fields = compatibility[
            1
        ]

        if not is_compatible:

            print(
                "\n===== DYNAMIC MODEL REJECTED ====="
            )

            print(
                "MODEL:",
                candidate_model
            )

            print(
                "MODEL SCORE:",
                model_score
            )

            print(
                "REASON:",
                "required fields/concepts not fully compatible"
            )

            continue

        compatibility_bonus = (
            len(
                required_fields
            )
            * 1000.0
        )

        exact_bonus = 0.0

        for source_field, resolved_field in (
            resolved_fields.items()
        ):

            if (
                source_field
                == resolved_field
            ):

                exact_bonus += 500.0

        final_score = (
            model_score
            + compatibility_bonus
            + exact_bonus
        )

        compatible_candidates.append(
            (
                final_score,
                candidate_model,
                model_record,
                candidate_fields,
                resolved_fields,
            )
        )

        print(
            "\n===== DYNAMIC MODEL ACCEPTED CANDIDATE ====="
        )

        print(
            "MODEL:",
            candidate_model
        )

        print(
            "MODEL SCORE:",
            model_score
        )

        print(
            "COMPATIBILITY BONUS:",
            compatibility_bonus
        )

        print(
            "EXACT BONUS:",
            exact_bonus
        )

        print(
            "FINAL SCORE:",
            final_score
        )

        print(
            "RESOLVED FIELDS:",
            resolved_fields
        )

    if not compatible_candidates:

        print(
            "\n===== DYNAMIC MODEL FALLBACK FAILED ====="
        )

        print(
            "NO COMPATIBLE MODEL FOUND"
        )

        return None

    compatible_candidates.sort(
        key=lambda item: (
            -item[0],
            item[1].lower(),
        )
    )

    (
        best_score,
        selected_model,
        selected_model_record,
        selected_fields,
        selected_resolved_fields,
    ) = compatible_candidates[0]

    print(
        "\n===== DYNAMIC MODEL FALLBACK SELECTED ====="
    )

    print(
        "CURRENT MODEL:",
        current_model
    )

    print(
        "SELECTED MODEL:",
        selected_model
    )

    print(
        "MODEL SCORE:",
        best_score
    )

    print(
        "RESOLVED FIELDS:",
        selected_resolved_fields
    )

    try:

        discovered_schema = await (
            metadata_service.discover_model_schema(
                selected_model
            )
        )

    except Exception as exc:

        print(
            "\n===== DYNAMIC FALLBACK METADATA ERROR ====="
        )

        print(
            "MODEL:",
            selected_model
        )

        print(
            "TYPE:",
            type(exc).__name__
        )

        print(
            "MESSAGE:",
            str(exc)
        )

        return None

    if not isinstance(
        discovered_schema,
        dict
    ):

        return None

    discovered_fields = (
        discovered_schema.get(
            "fields",
            {}
        )
    )

    discovered_metadata = (
        discovered_schema.get(
            "metadata",
            {}
        )
    )

    if not isinstance(
        discovered_fields,
        dict
    ):

        discovered_fields = {}

    if not isinstance(
        discovered_metadata,
        dict
    ):

        discovered_metadata = {}

    print(
        "\n===== DYNAMIC FALLBACK FULL METADATA VALIDATION ====="
    )

    print(
        "MODEL:",
        selected_model
    )

    print(
        "FIELDS:",
        len(discovered_fields)
    )

    final_compatibility = (
        _dynamic_required_fields_compatible(
            params=params,
            fields=discovered_fields,
            user_message=user_message,
        )
    )

    if not final_compatibility[0]:

        print(
            "\n===== DYNAMIC FALLBACK FINAL REJECT ====="
        )

        print(
            "MODEL:",
            selected_model
        )

        print(
            "REASON:",
            "full metadata validation failed"
        )

        return None

    final_resolved_fields = (
        final_compatibility[1]
    )

    print(
        "\n===== DYNAMIC FALLBACK FINAL ACCEPT ====="
    )

    print(
        "MODEL:",
        selected_model
    )

    print(
        "FINAL RESOLVED FIELDS:",
        final_resolved_fields
    )

    return (
        selected_model,
        discovered_fields,
        discovered_metadata,
    )


# ==========================================================
# ODOO AGENT
# ==========================================================

async def odoo_agent(
    state
):

    print(
        "Portant DYNAMIC AGENT ESEGUITO"
    )

    # ======================================================
    # CURRENT USER MESSAGE
    # ======================================================

    state_messages = (
        state.get(
            "messages",
            []
        )
    )

    current_user_message = ""

    if state_messages:

        last_message = (
            state_messages[-1]
        )

        current_user_message = (
            getattr(
                last_message,
                "content",
                ""
            )
            or ""
        )

    current_user_message = str(
        current_user_message
    ).strip()

    # ======================================================
    # PLAN
    # ======================================================

    plan = (
        state.get(
            "plan"
        )
        or {}
    )

    if not isinstance(
        plan,
        dict
    ):

        raise ValueError(
            "Piano Portant non valido."
        )

    # ======================================================
    # NORMALIZZAZIONE
    # ======================================================

    parameters = (
        _normalize_parameters(
            plan
        )
    )

    model = parameters.get(
        "model"
    )

    method = parameters.get(
        "method"
    )

    params = parameters.get(
        "params"
    )

    if not model:

        raise ValueError(
            "Il piano Portant non contiene il modello."
        )

    if not method:

        raise ValueError(
            "Il piano Portant non contiene il metodo."
        )

    if not isinstance(
        params,
        dict
    ):

        raise ValueError(
            "Il piano Portant contiene parametri non validi."
        )

    # ======================================================
    # READ_GROUP ORDERBY
    # ======================================================

    if method == "read_group":

        params = (
            _normalize_read_group_orderby(
                params
            )
        )

    print(
        "\n===== Portant PLAN ====="
    )

    print(
        {
            "agent":
                plan.get(
                    "agent"
                ),

            "action":
                plan.get(
                    "action"
                ),

            "domain":
                params.get(
                    "domain",
                    plan.get(
                        "domain"
                    )
                ),

            "parameters": {

                "model":
                    model,

                "method":
                    method,

                "params":
                    params,

            }

        }
    )

    # ======================================================
    # DOMAIN RESOLVER
    # ======================================================

    from app.services.odoo_domain_resolver import (
        OdooDomainResolver
    )

    plan_domain = (
        params.get(
            "domain"
        )
    )

    if plan_domain is None:

        plan_domain = (
            plan.get(
                "domain"
            )
            or []
        )

    resolved = (
        OdooDomainResolver.resolve(
            domain=plan_domain,

            parameters={

                "model":
                    model,

                "method":
                    method,

                "params":
                    params,

            }
        )
    )

    if not isinstance(
        resolved,
        dict
    ):

        raise ValueError(
            "Il DomainResolver ha restituito parametri non validi."
        )

    parameters = (
        resolved
    )

    # ======================================================
    # RIALLINEAMENTO
    # ======================================================

    model = parameters.get(
        "model",
        model
    )

    method = parameters.get(
        "method",
        method
    )

    params = (
        parameters.get(
            "params",
            {}
        )
    )

    if not isinstance(
        params,
        dict
    ):

        params = {}

    params = (
        _normalize_nested_params(
            params
        )
    )

    # ======================================================
    # PARTNER RESOLVER
    # ======================================================

    model, method, params = (
        await _resolve_partner_domain(
            model=model,
            method=method,
            params=params
        )
    )

    print(
        "\n===== POST PARTNER RESOLUTION ====="
    )

    print(
        "MODEL:",
        model
    )

    print(
        "METHOD:",
        method
    )

    print(
        "DOMAIN:",
        params.get(
            "domain",
            []
        )
    )

    # ======================================================
    # DOMAIN DEFAULT
    # ======================================================

    params = (
        _normalize_nested_params(
            params
        )
    )

    if "domain" not in params:

        params["domain"] = []

    # ======================================================
    # SANITIZATION
    # ======================================================

    params["domain"] = (
        _sanitize_domain_against_user_intent(
            model=model,
            domain=params.get(
                "domain",
                []
            ),
            user_message=current_user_message
        )
    )

    # ======================================================
    # READ_GROUP ORDERBY
    # ======================================================

    if method == "read_group":

        params = (
            _normalize_read_group_orderby(
                params
            )
        )

    # ======================================================
    # PARAMETRI FINALI PRIMA DEI METADATA
    # ======================================================

    parameters["model"] = model
    parameters["method"] = method
    parameters["params"] = params

    # ======================================================
    # ODOO CLIENT
    # ======================================================

    odoo_client = (
        get_odoo_client()
    )

    if odoo_client is None:

        raise ValueError(
            "Nessun client Portant associato alla sessione corrente."
        )

    # ======================================================
    # METADATA ODOO REALI
    # ======================================================

    print(
        "\n===== MODEL DISCOVERY ====="
    )

    print(
        "MODEL:",
        model
    )

    from app.services.odoo_metadata_service import (
        OdooMetadataService
    )

    from app.services.odoo_validator import (
        ODOO_MODELS
    )

    metadata_service = (
        OdooMetadataService(
            odoo_client=odoo_client
        )
    )

    is_static_model = (
        model in ODOO_MODELS
    )

    if is_static_model:

        print(
            "MODEL FOUND IN STATIC CATALOG"
        )

        print(
            "STATIC CATALOG USED ONLY AS MODEL POLICY"
        )

        print(
            "LOADING REAL ODOO FIELD METADATA..."
        )

    else:

        print(
            "MODEL NOT IN STATIC CATALOG"
        )

        print(
            "STARTING DYNAMIC DISCOVERY..."
        )

    discovered_schema = None

    try:

        discovered_schema = await (
            metadata_service.discover_model_schema(
                model
            )
        )

    except Exception as exc:

        print(
            "\n===== ODOO FIELD DISCOVERY ERROR ====="
        )

        print(
            "MODEL:",
            model
        )

        print(
            "TYPE:",
            type(exc).__name__
        )

        print(
            "MESSAGE:",
            str(exc)
        )

    # ======================================================
    # MODELLO NON ESISTENTE
    # ======================================================

    if discovered_schema is None:

        if not is_static_model:

            print(
                "DYNAMIC DISCOVERY: MODEL NOT FOUND"
            )

            raise ValueError(
                "Il modello Portant richiesto non esiste "
                f"nell'istanza Odoo: {model}"
            )

        print(
            "\n===== REAL MODEL METADATA UNAVAILABLE ====="
        )

        print(
            "MODEL:",
            model
        )

    else:

        discovered_metadata = (
            discovered_schema.get(
                "metadata",
                {}
            )
        )

        discovered_fields = (
            discovered_schema.get(
                "fields",
                {}
            )
        )

        if not isinstance(
            discovered_metadata,
            dict
        ):

            discovered_metadata = {}

        if not isinstance(
            discovered_fields,
            dict
        ):

            discovered_fields = {}

        print(
            "\n===== ODOO FIELD METADATA LOADED ====="
        )

        print(
            "MODEL:",
            model
        )

        print(
            "FIELDS:",
            len(
                discovered_fields
            )
        )

        # --------------------------------------------------
        # DEBUG DINAMICO DELLE RELAZIONI
        # --------------------------------------------------

        relation_fields = []

        for field_name, field_meta in discovered_fields.items():

            if not isinstance(
                field_meta,
                dict
            ):

                continue

            field_type = str(
                field_meta.get(
                    "type",
                    field_meta.get(
                        "ttype",
                        ""
                    )
                )
                or ""
            ).lower()

            relation = (
                field_meta.get(
                    "relation"
                )
            )

            if (
                field_type == "many2one"
                and relation
            ):

                relation_fields.append(
                    (
                        field_name,
                        relation,
                        field_meta.get(
                            "string",
                            field_meta.get(
                                "field_description",
                                ""
                            )
                        )
                    )
                )

        print(
            "\n===== DYNAMIC RELATION FIELDS ====="
        )

        for (
            relation_field_name,
            relation_model,
            relation_label,
        ) in relation_fields:

            print(
                " -",
                relation_field_name,
                "|",
                relation_label,
                "| relation:",
                relation_model
            )

        # --------------------------------------------------
        # REGISTRAZIONE MODELLO DINAMICO
        # --------------------------------------------------

        if not is_static_model:

            odoo_validator.register_dynamic_model(

                model=model,

                metadata=discovered_metadata,

                fields=discovered_fields,

            )

            odoo_validator.register_dynamic_fields(
                model=model,
                fields=discovered_fields,
            )

        # ==================================================
        # MODEL COMPATIBILITY CHECK
        # ==================================================

        model_compatibility = (
            _dynamic_required_fields_compatible(
                params=params,
                fields=discovered_fields,
                user_message=current_user_message,
            )
        )

        if not model_compatibility[0]:

            print(
                "\n===== CURRENT MODEL REJECTED ====="
            )

            print(
                "MODEL:",
                model
            )

            print(
                "REASON:",
                "required query fields are not compatible"
            )

            fallback_result = await (
                _dynamic_find_compatible_model(
                    odoo_client=odoo_client,

                    metadata_service=metadata_service,

                    current_model=model,

                    current_metadata=discovered_metadata,

                    current_fields=discovered_fields,

                    params=params,

                    user_message=current_user_message,
                )
            )

            if fallback_result is None:

                raise ValueError(
                    "Nessun modello Odoo compatibile "
                    "è stato trovato dinamicamente "
                    "per soddisfare la richiesta."
                )

            (
                fallback_model,
                fallback_fields,
                fallback_metadata,
            ) = fallback_result

            print(
                "\n===== MODEL FALLBACK APPLIED ====="
            )

            print(
                "ORIGINAL MODEL:",
                model
            )

            print(
                "FALLBACK MODEL:",
                fallback_model
            )

            model = (
                fallback_model
            )

            discovered_fields = (
                fallback_fields
            )

            discovered_metadata = (
                fallback_metadata
            )

            parameters["model"] = (
                model
            )

            if model not in ODOO_MODELS:

                odoo_validator.register_dynamic_model(

                    model=model,

                    metadata=discovered_metadata,

                    fields=discovered_fields,

                )

                odoo_validator.register_dynamic_fields(
                    model=model,
                    fields=discovered_fields,
                )

        # ==================================================
        # DYNAMIC FIELD / GROUPBY / ORDERBY RESOLUTION
        # ==================================================

        params = _dynamic_apply_field_resolution(
            params=params,
            fields=discovered_fields,
            user_message=current_user_message,
        )

        # ==================================================
        # INVALID FIELDS
        # ==================================================

        params = _dynamic_remove_invalid_fields(
            params=params,
            fields=discovered_fields,
        )

        # ======================================================
        # FINAL GROUPBY TYPE NORMALIZATION
        # ======================================================

        groupby = params.get(
            "groupby"
        )

        if isinstance(
            groupby,
            str
        ):

            params["groupby"] = [
                groupby
            ]

        elif groupby is None:

            params["groupby"] = []

        print(
            "\n===== FINAL GROUPBY ====="
        )

        print(
            "GROUPBY:",
            params.get(
                "groupby",
                []
            )
        )

        # ==================================================
        # DYNAMIC DOMAIN RESOLUTION
        # ==================================================

        params = _dynamic_repair_domain(
            params=params,
            fields=discovered_fields,
            user_message=current_user_message,
        )

        print(
            "\n===== ODOO PARAMETERS RESOLVED ====="
        )

        print(
            "FIELDS:",
            params.get(
                "fields",
                []
            )
        )

        print(
            "GROUPBY:",
            params.get(
                "groupby",
                []
            )
        )

        print(
            "ORDERBY:",
            params.get(
                "orderby"
            )
        )

        print(
            "ORDER:",
            params.get(
                "order"
            )
        )

        print(
            "DOMAIN:",
            params.get(
                "domain",
                []
            )
        )

    # ======================================================
    # RIALLINEAMENTO PARAMETRI
    # ======================================================

    parameters["model"] = model
    parameters["method"] = method
    parameters["params"] = params

    # ======================================================
    # VALIDATION
    # ======================================================

    print(
        "\n===== VALIDATING Portant PARAMETERS ====="
    )

    validated = (
        odoo_validator.validate(
            parameters
        )
    )

    print(
        "\n===== VALIDATED PARAMETERS ====="
    )

    print(
        validated
    )

    # ======================================================
    # PROTEZIONE CONTRO PERDITA DI PARAMETRI
    # ======================================================

    validated = (
        _dynamic_reapply_resolved_parameter_fields(
            parameters=validated,
            source_params=params,
        )
    )

    final_params = (
        validated.get(
            "params",
            {}
        )
    )

    if not isinstance(
        final_params,
        dict
    ):

        final_params = {}

    final_params = (
        _normalize_nested_params(
            final_params
        )
    )

    if "domain" not in final_params:

        final_params["domain"] = []

    if method == "read_group":

        final_params = (
            _normalize_read_group_orderby(
                final_params
            )
        )

    validated["params"] = (
        final_params
    )

    # Il modello può essere stato cambiato dal fallback.
    validated["model"] = (
        model
    )

    validated["method"] = (
        method
    )

    print(
        "\n===== FINAL ODOO PARAMETERS ====="
    )

    print(
        "MODEL:",
        model
    )

    print(
        "METHOD:",
        method
    )

    print(
        "FIELDS:",
        final_params.get(
            "fields",
            []
        )
    )

    print(
        "GROUPBY:",
        final_params.get(
            "groupby",
            []
        )
    )

    print(
        "ORDERBY:",
        final_params.get(
            "orderby"
        )
    )

    print(
        "DOMAIN:",
        final_params.get(
            "domain",
            []
        )
    )

    endpoint = (
        f"/api/{model}/{method}"
    )

    result = None

    # ======================================================
    # READ_GROUP
    # ======================================================

    if method == "read_group":

        domain = (
            final_params.get(
                "domain",
                []
            )
        )

        fields = (
            final_params.get(
                "fields",
                []
            )
        )

        groupby = (
            final_params.get(
                "groupby",
                []
            )
        )

        offset = (
            final_params.get(
                "offset",
                0
            )
        )

        limit = (
            final_params.get(
                "limit",
                10
            )
        )

        orderby = (
            final_params.get(
                "orderby"
            )
        )

        lazy = (
            final_params.get(
                "lazy",
                False
            )
        )

        aggregate_fields = (
            _extract_aggregate_fields(
                fields
            )
        )

        count_grouping_requested = (
            isinstance(
                orderby,
                str
            )
            and "__count" in orderby
        )

        if (
            aggregate_fields
            or count_grouping_requested
        ):

            result = await (
                _python_aggregate_read_group(
                    odoo_client=odoo_client,

                    model=model,

                    domain=domain,

                    fields=fields,

                    groupby=groupby,

                    orderby=orderby,

                    limit=limit,

                    offset=offset,
                )
            )

        else:

            print(
                "\n===== Portant NATIVE CALL_KW ====="
            )

            print(
                "URL:",
                (
                    f"{odoo_client.base_url}"
                    f"/web/dataset/call_kw/"
                    f"{model}/read_group"
                )
            )

            print(
                "MODEL:",
                model
            )

            print(
                "METHOD:",
                "read_group"
            )

            print(
                "ARGS:",
                [
                    domain,
                    fields,
                    groupby,
                ]
            )

            print(
                "KWARGS:",
                {

                    "offset":
                        offset,

                    "limit":
                        limit,

                    "orderby":
                        orderby,

                    "lazy":
                        lazy,

                }
            )

            result = await (
                odoo_client.call_kw(
                    model=model,

                    method="read_group",

                    args=[
                        domain,
                        fields,
                        groupby,
                    ],

                    kwargs={

                        "offset":
                            offset,

                        "limit":
                            limit,

                        "orderby":
                            orderby,

                        "lazy":
                            lazy,

                    },

                )
            )

    # ======================================================
    # SEARCH_READ / SEARCH_COUNT / ALTRI
    # ======================================================

    else:

        print(
            "\n===== Portant REQUEST ====="
        )

        print(
            "URL:",
            (
                f"{odoo_client.base_url}"
                f"{endpoint}"
            )
        )

        print(
            "BODY:",
            final_params
        )

        result = await (
            odoo_client.call(
                endpoint,
                body=final_params
            )
        )

    # ======================================================
    # NORMALIZZAZIONE
    # ======================================================

    normalized = (
        _normalize_odoo_result(
            result=result,
            method=method,
            params=final_params,
        )
    )

    print(
        "\n===== Portant NORMALIZED RESULT ====="
    )

    print(
        "TYPE:",
        normalized.get(
            "type"
        )
    )

    print(
        "COUNT:",
        normalized.get(
            "count"
        )
    )

    print(
        "TOTAL RECORDS:",
        normalized[
            "pagination"
        ].get(
            "total_records"
        )
    )

    print(
        "RETURNED RECORDS:",
        normalized[
            "pagination"
        ].get(
            "returned_records"
        )
    )

    print(
        "LIMIT:",
        normalized[
            "pagination"
        ].get(
            "limit"
        )
    )

    print(
        "OFFSET:",
        normalized[
            "pagination"
        ].get(
            "offset"
        )
    )

    print(
        "PAGES:",
        normalized[
            "pagination"
        ].get(
            "pages"
        )
    )

    print(
        "HAS MORE:",
        normalized[
            "pagination"
        ].get(
            "has_more"
        )
    )

    # ======================================================
    # OUTPUT STATE
    # ======================================================

    return {

        "plan": {

            **plan,

            "parameters":
                validated,

        },

        "odoo_data":
            normalized,

    }