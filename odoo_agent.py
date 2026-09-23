import re

from typing import Any, Dict, List, Optional, Tuple

from app.services.odoo_validator import (
    odoo_validator
)

from app.services.request_context import (
    get_odoo_client
)

from urllib.parse import quote


# ==========================================================
# GENERIC HELPERS
# ==========================================================

def _looks_like_odoo_model(
    value: Any
) -> bool:

    if not isinstance(
        value,
        str
    ):
        return False

    text = value.strip()

    if not text:
        return False

    return bool(
        re.match(
            r"^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+$",
            text
        )
    )


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

    planner_domain_hint = parameters.get(
        "domain"
    )

    if (
        not model
        and _looks_like_odoo_model(
            planner_domain_hint
        )
    ):

        model = (
            planner_domain_hint.strip()
        )

        print(
            "\n===== PLANNER MODEL HINT RECOVERED ====="
        )

        print(
            "MODEL RECOVERED FROM PARAMETERS.DOMAIN:",
            model
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

        if (
            key == "domain"
            and _looks_like_odoo_model(
                value
            )
        ):
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

    if field.endswith(
        "_count"
    ):

        print(
            "\n===== ORDERBY COUNT NORMALIZATION ====="
        )

        print(
            "ORIGINAL ORDERBY:",
            orderby
        )

        print(
            "NORMALIZED ORDERBY:",
            f"__count {direction}"
        )

        params["orderby"] = (
            f"__count {direction}"
        )

        return params

    aggregate_suffixes = (
        "_sum",
        "_avg",
        "_min",
        "_max",
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
# ODOO RECORD LINKS
# ==========================================================

def _attach_record_links(
    normalized: Dict[str, Any],
    model: str,
    base_url: str,
) -> Dict[str, Any]:

    if not isinstance(
        normalized,
        dict
    ):
        return normalized

    if normalized.get(
        "type"
    ) != "records":

        return normalized

    records = normalized.get(
        "records"
    )

    if not isinstance(
        records,
        list
    ):
        return normalized

    if not isinstance(
        model,
        str
    ) or not model.strip():

        return normalized

    if not isinstance(
        base_url,
        str
    ) or not base_url.strip():

        return normalized

    clean_base_url = base_url.rstrip("/")

    links: List[
        Dict[str, Any]
    ] = []

    for record in records:

        if not isinstance(
            record,
            dict
        ):
            continue

        raw_id = record.get(
            "id"
        )

        try:

            record_id = int(
                raw_id
            )

        except (
            TypeError,
            ValueError
        ):

            continue

        if record_id <= 0:
            continue

        label = (
            record.get(
                "display_name"
            )
            or record.get(
                "name"
            )
            or record_id
        )

        if isinstance(
            label,
            (list, tuple)
        ):

            if len(label) >= 2:

                label = label[1]

            elif len(label) == 1:

                label = label[0]

        if isinstance(
            label,
            dict
        ):

            label = (
                label.get(
                    "display_name"
                )
                or label.get(
                    "name"
                )
                or label.get(
                    "id"
                )
                or record_id
            )

        label = str(
            label
        )

        encoded_model = quote(
            model,
            safe=""
        )

        url = (
            f"{clean_base_url}"
            f"/web#id={record_id}"
            f"&model={encoded_model}"
            f"&view_type=form"
        )

        links.append({
            "id":
                record_id,

            "model":
                model,

            "label":
                label,

            "url":
                url,
        })

    if links:

        normalized[
            "record_links"
        ] = links

    return normalized


# ==========================================================
# USER INTENT / DOMAIN SANITIZATION
# ==========================================================

def _has_explicit_numeric_record_id(
    user_message: str
) -> bool:

    return bool(
        re.search(
            r"\b(?:record\s+id|"
            r"id)"
            r"\s*(?:=|==|:|è|e)?\s*\d+\b",
            user_message or "",
            flags=re.IGNORECASE,
        )
    )


def _is_numeric_identifier_value(
    value: Any
) -> bool:

    if isinstance(
        value,
        bool
    ):

        return True

    if isinstance(
        value,
        int
    ):

        return True

    if isinstance(
        value,
        list
    ):

        if not value:
            return False

        return all(
            isinstance(
                item,
                int
            )
            or isinstance(
                item,
                bool
            )
            for item in value
        )

    return False


def _sanitize_domain_against_user_intent(
    model: str,
    domain: Any,
    user_message: str
) -> Any:

    """
    Sanitizzazione esclusivamente tecnica.

    Non contiene conoscenza semantica su clienti, fornitori,
    prodotti o altri domini applicativi.

    Protegge soltanto da filtri numerici artificiali su `id`
    quando l'utente non ha richiesto esplicitamente un ID.
    """

    if not isinstance(
        domain,
        list
    ):
        return []

    has_explicit_numeric_record_id = (
        _has_explicit_numeric_record_id(
            user_message
        )
    )

    sanitized = []

    for item in domain:

        if isinstance(
            item,
            str
        ):

            if item in {
                "&",
                "|",
                "!",
            }:

                sanitized.append(
                    item
                )

            continue

        if not isinstance(
            item,
            list
        ):
            continue

        if len(item) != 3:
            continue

        field = item[0]
        operator = item[1]
        value = item[2]

        if not isinstance(
            field,
            str
        ):
            continue

        if not isinstance(
            operator,
            str
        ):
            continue

        field = field.strip()
        operator = operator.strip()

        if (
            field == "id"
            and _is_numeric_identifier_value(
                value
            )
            and operator in {
                "=",
                "!=",
                "in",
                "not in",
            }
            and not has_explicit_numeric_record_id
        ):

            print(
                "\n===== DOMAIN SANITIZATION ====="
            )

            print(
                "REMOVED UNGROUNDED RECORD ID FILTER:",
                item
            )

            continue

        sanitized.append(
            item
        )

    return sanitized


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
    ):

        limit = 10

    if limit < 0:
        limit = 10

    if limit == 0:

        returned_rows = rows[
            offset:
        ]

        has_more = False

        limit_value = len(
            returned_rows
        )

        pages = (
            1
            if returned_rows
            else 0
        )

    else:

        returned_rows = rows[
            offset:
            offset + limit
        ]

        has_more = (
            offset
            + len(returned_rows)
            < total_groups
        )

        limit_value = limit

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
                limit_value,

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

DYNAMIC_DATE_GRANULARITIES = {
    "month",
    "week",
    "day",
    "quarter",
    "year",
}

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
    user_message: str,
    semantic_concepts: Optional[
        List[Dict[str, Any]]
    ] = None,
    groupby: Optional[Any] = None,
    orderby: Optional[Any] = None,
) -> float:
    """
    Calcola quanto un campo sia utile come campo human-facing
    predefinito.

    La selezione è interamente metadata-driven.

    NON contiene mapping specifici del tipo:

        modello -> campo
        concetto -> technical field

    Il ranking usa esclusivamente:
    - nome tecnico;
    - label;
    - help;
    - tipo Odoo;
    - relazione;
    - semantica della richiesta;
    - ruolo generico del campo.
    """

    if not isinstance(
        field_meta,
        dict,
    ):
        field_meta = {}

    field_name = str(
        field_name or ""
    ).strip()

    user_message = str(
        user_message or ""
    ).strip()

    semantic_concepts = (
        semantic_concepts
        if isinstance(
            semantic_concepts,
            list,
        )
        else []
    )

    score = 0.0

    field_type = str(
        field_meta.get(
            "type",
            field_meta.get(
                "ttype",
                ""
            ),
        )
        or ""
    ).strip().lower()

    field_label = str(
        field_meta.get(
            "string",
            field_meta.get(
                "label",
                "",
            ),
        )
        or ""
    ).strip()

    field_help = str(
        field_meta.get(
            "help",
            "",
        )
        or ""
    ).strip()

    relation = str(
        field_meta.get(
            "relation",
            "",
        )
        or ""
    ).strip()

    field_text = " ".join(
        value
        for value in (
            field_name,
            field_label,
            field_help,
        )
        if value
    ).lower()

    # ======================================================
    # TOKENIZATION
    # ======================================================

    field_tokens = set(
        re.findall(
            r"[a-zA-ZÀ-ÿ0-9_]+",
            field_text,
        )
    )

    technical_tokens = set(
        re.findall(
            r"[a-zA-ZÀ-ÿ0-9_]+",
            field_name.lower(),
        )
    )

    user_tokens = set(
        re.findall(
            r"[a-zA-ZÀ-ÿ0-9_]+",
            user_message.lower(),
        )
    )

    # ======================================================
    # GENERIC TECHNICAL / PRESENTATION TYPES
    # ======================================================

    if field_type in {
        "char",
        "text",
        "html",
        "selection",
        "date",
        "datetime",
        "integer",
        "float",
        "monetary",
        "many2one",
    }:
        score += 20.0

    elif field_type in {
        "boolean",
    }:
        score += 8.0

    elif field_type in {
        "one2many",
        "many2many",
        "binary",
    }:
        score -= 35.0

    # ======================================================
    # BASE BUSINESS / IDENTITY FIELDS
    # ======================================================

    identity_tokens = {
        "name",
        "reference",
        "ref",
        "number",
        "code",
        "identifier",
        "description",
        "label",
    }

    identity_hits = (
        len(
            technical_tokens
            & identity_tokens
        )
    )

    if identity_hits:
        score += (
            identity_hits
            * 35.0
        )

    # ======================================================
    # BUSINESS DATE / AMOUNT / QUANTITY / STATUS
    # ======================================================

    business_tokens = {
        "date",
        "order",
        "document",
        "created",
        "approved",
        "confirmation",
        "delivery",
        "shipping",
        "expected",
        "planned",
        "deadline",
        "due",
        "amount",
        "total",
        "subtotal",
        "price",
        "value",
        "cost",
        "tax",
        "quantity",
        "qty",
        "status",
        "state",
        "available",
        "availability",
    }

    business_hits = (
        len(
            field_tokens
            & business_tokens
        )
    )

    if business_hits:
        score += (
            business_hits
            * 18.0
        )

    # ======================================================
    # COMMERCIAL COUNTERPARTY
    # ======================================================
    #
    # Regola volutamente generica:
    # non conosce il modello Odoo e non conosce il nome
    # tecnico del campo.
    #
    # Cerca nei metadata del campo indicazioni che
    # rappresentino una controparte commerciale.

    counterparty_tokens = {
        "customer",
        "customers",
        "client",
        "clients",
        "cliente",
        "clienti",
        "vendor",
        "vendors",
        "supplier",
        "suppliers",
        "fornitore",
        "fornitori",
        "partner",
        "partners",
        "buyer",
        "buyers",
        "acquirente",
        "acquirenti",
        "purchaser",
        "purchasers",
    }

    counterparty_hits = (
        len(
            field_tokens
            & counterparty_tokens
        )
    )

    if (
        field_type == "many2one"
        and counterparty_hits
    ):

        # Bonus forte: una relazione many2one descritta
        # nei metadata come controparte commerciale è
        # normalmente molto utile nella rappresentazione
        # di un record business.
        score += 85.0

        # Bonus aggiuntivo quando la label stessa è
        # praticamente la controparte.
        label_tokens = set(
            re.findall(
                r"[a-zA-ZÀ-ÿ0-9_]+",
                field_label.lower(),
            )
        )

        label_counterparty_hits = (
            len(
                label_tokens
                & counterparty_tokens
            )
        )

        if label_counterparty_hits:
            score += 25.0

    # ======================================================
    # PARTNER GENERICO
    # ======================================================

    if (
        field_type == "many2one"
        and "partner" in field_tokens
    ):

        score += 45.0

    # ======================================================
    # REFERENCE DI UNA CONTROPARTE
    # ======================================================
    #
    # Campi tipo:
    #
    #   Customer Reference
    #   Partner Reference
    #   Vendor Reference
    #
    # restano utili, ma devono stare normalmente sotto
    # la relazione vera e propria con la controparte.

    reference_hits = (
        len(
            field_tokens
            & {
                "reference",
                "ref",
                "riferimento",
            }
        )
    )

    if (
        counterparty_hits
        and reference_hits
    ):

        score -= 28.0

    # ======================================================
    # REQUEST OVERLAP
    # ======================================================

    if user_tokens:

        request_hits = (
            len(
                field_tokens
                & user_tokens
            )
        )

        if request_hits:
            score += (
                request_hits
                * 12.0
            )

    # ======================================================
    # SEMANTIC CONCEPT OVERLAP
    # ======================================================

    concept_texts = []

    for concept in semantic_concepts:

        if isinstance(
            concept,
            str,
        ):

            concept_texts.append(
                concept
            )

        elif isinstance(
            concept,
            dict,
        ):

            concept_name = concept.get(
                "concept"
            )

            if isinstance(
                concept_name,
                str,
            ):

                concept_texts.append(
                    concept_name
                )

            queries = concept.get(
                "queries",
                []
            )

            if isinstance(
                queries,
                list,
            ):

                concept_texts.extend(
                    query
                    for query in queries
                    if isinstance(
                        query,
                        str,
                    )
                )

    concept_tokens = set(
        re.findall(
            r"[a-zA-ZÀ-ÿ0-9_]+",
            " ".join(
                concept_texts
            ).lower(),
        )
    )

    concept_hits = (
        len(
            field_tokens
            & concept_tokens
        )
    )

    if concept_hits:
        score += (
            concept_hits
            * 14.0
        )

    # ======================================================
    # GROUPBY / ORDERBY RELEVANCE
    # ======================================================

    groupby_values = []

    if isinstance(
        groupby,
        str,
    ):

        groupby_values = [
            groupby
        ]

    elif isinstance(
        groupby,
        list,
    ):

        groupby_values = [
            value
            for value in groupby
            if isinstance(
                value,
                str,
            )
        ]

    for groupby_value in groupby_values:

        if field_name == groupby_value.strip():

            score += 80.0

    orderby_text = ""

    if isinstance(
        orderby,
        str,
    ):

        orderby_text = orderby.lower()

    elif isinstance(
        orderby,
        list,
    ):

        orderby_text = " ".join(
            str(value)
            for value in orderby
        ).lower()

    if (
        orderby_text
        and field_name.lower()
        in orderby_text
    ):

        score += 50.0

    # ======================================================
    # REQUIRED / STORED
    # ======================================================

    if field_meta.get(
        "required"
    ):
        score += 12.0

    if field_meta.get(
        "store"
    ):
        score += 8.0

    # ======================================================
    # TECHNICAL / ADMIN / INTERNAL PENALTIES
    # ======================================================

    technical_penalty_tokens = {
        "activity",
        "audit",
        "tracking",
        "technical",
        "internal",
        "access",
        "permission",
        "checksum",
        "hash",
        "index",
        "mail",
        "message",
        "notification",
        "sequence",
        "sync",
        "integration",
        "external",
        "uuid",
        "token",
        "debug",
        "log",
        "create",
        "write",
        "update",
        "last_update",
    }

    technical_hits = (
        len(
            field_tokens
            & technical_penalty_tokens
        )
    )

    if technical_hits:
        score -= (
            technical_hits
            * 35.0
        )

    # ======================================================
    # TECHNICAL MULTI-VALUE RELATIONS
    # ======================================================

    if field_name.lower().endswith(
        "_ids"
    ):

        score -= 30.0

    # ======================================================
    # DATETIME TECHNICAL UPDATE FIELDS
    # ======================================================

    technical_datetime_tokens = {
        "create",
        "created",
        "write",
        "updated",
        "update",
        "last",
        "modified",
    }

    if (
        field_type in {
            "date",
            "datetime",
        }
        and (
            field_tokens
            & technical_datetime_tokens
        )
    ):

        score -= 28.0

    # ======================================================
    # FALSE "PARTY REFERENCE" DOMINATION PROTECTION
    # ======================================================
    #
    # Evita che un campo testuale come:
    #
    #   partner_ref
    #   client_order_ref
    #
    # superi una vera relazione many2one Customer/Vendor.

    if (
        counterparty_hits
        and reference_hits
        and field_type != "many2one"
    ):

        score -= 18.0

    # ======================================================
    # RELATION TYPE BONUS
    # ======================================================

    if field_type == "many2one":

        score += 12.0

        if relation:
            score += 4.0

    # ======================================================
    # FINAL NORMALIZATION
    # ======================================================

    return float(
        round(
            score,
            3,
        )
    )

def _dynamic_default_fields(
    fields: Dict[str, Dict[str, Any]],
    limit: int = 8,
    user_message: str = "",
    semantic_concepts: Optional[
        List[Dict[str, Any]]
    ] = None,
    groupby: Optional[List[Any]] = None,
    orderby: Optional[str] = None,
    tree_view: Optional[Dict[str, Any]] = None,
) -> List[str]:

    if not isinstance(
        fields,
        dict
    ):

        return []

    if not fields:

        return []

    # ======================================================
    # PRIORITÀ 1:
    # TREE VIEW REALE ODOO
    #
    # La tree/list view rappresenta la presentazione
    # definita direttamente da Odoo.
    #
    # Nessun modello o campo è hardcoded.
    # ======================================================

    if isinstance(
        tree_view,
        dict,
    ):

        visible_field_names = (
            tree_view.get(
                "visible_field_names",
                []
            )
        )

        if isinstance(
            visible_field_names,
            list
        ):

            view_fields = []

            seen_fields = set()

            for field_name in visible_field_names:

                if not isinstance(
                    field_name,
                    str
                ):

                    continue

                field_name = (
                    field_name.strip()
                )

                if not field_name:

                    continue

                if field_name in seen_fields:

                    continue

                # ------------------------------------------
                # La view è autorevole sulla presentazione,
                # ma il campo deve comunque esistere nei
                # metadata ir.model.fields caricati.
                # ------------------------------------------

                if field_name not in fields:

                    print(
                        "\n===== TREE VIEW FIELD SKIPPED ====="
                    )

                    print(
                        "FIELD:",
                        field_name
                    )

                    print(
                        "REASON:",
                        "field not present in discovered Odoo metadata"
                    )

                    continue

                seen_fields.add(
                    field_name
                )

                view_fields.append(
                    field_name
                )

            if view_fields:

                print(
                    "\n===== DYNAMIC HUMAN FIELDS FROM ODOO TREE VIEW ====="
                )

                print(
                    "TREE VIEW:",
                    tree_view.get(
                        "view_id"
                    )
                )

                print(
                    "TREE VIEW STRING:",
                    tree_view.get(
                        "string"
                    )
                )

                print(
                    "TREE VIEW FIELDS:",
                    view_fields
                )

                return view_fields

    # ======================================================
    # PRIORITÀ 2:
    # FALLBACK ALLO SCORING DINAMICO ATTUALE
    # ======================================================

    candidates = []

    for field_name, field_meta in fields.items():

        if not isinstance(
            field_meta,
            dict
        ):
            continue

        score = _dynamic_field_display_score(
            field_name=field_name,
            field_meta=field_meta,
            user_message=user_message,
            semantic_concepts=semantic_concepts,
            groupby=groupby,
            orderby=orderby,
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

    for score, field_name in candidates:

        if field_name in result:
            continue

        result.append(
            field_name
        )

        print(
            "\n===== DYNAMIC HUMAN FIELD CANDIDATE ====="
        )

        print(
            "FIELD:",
            field_name
        )

        print(
            "SCORE:",
            score
        )

        if len(result) >= limit:
            break

    return result

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
# GENERIC SEMANTIC TOKEN ANALYSIS
# ==========================================================

def _dynamic_token_frequency(
    fields: Dict[str, Dict[str, Any]]
) -> Dict[str, int]:

    frequency: Dict[str, int] = {}

    if not isinstance(
        fields,
        dict
    ):

        return frequency

    for field_name, field_meta in fields.items():

        if not isinstance(
            field_meta,
            dict
        ):

            continue

        metadata_text = " ".join(
            [
                str(
                    field_name or ""
                ),
                str(
                    field_meta.get(
                        "string",
                        field_meta.get(
                            "field_description",
                            ""
                        )
                    )
                    or ""
                ),
                str(
                    field_meta.get(
                        "help",
                        ""
                    )
                    or ""
                ),
                str(
                    field_meta.get(
                        "relation",
                        ""
                    )
                    or ""
                ),
            ]
        )

        tokens = set(
            _normalize_semantic_tokens(
                metadata_text
            )
        )

        for token in tokens:

            frequency[token] = (
                frequency.get(
                    token,
                    0
                )
                + 1
            )

    return frequency


def _dynamic_non_generic_tokens(
    tokens: List[str],
    fields: Optional[
        Dict[str, Dict[str, Any]]
    ] = None,
) -> List[str]:

    if not isinstance(
        tokens,
        list
    ):

        return []

    if not fields:

        return [
            token
            for token in tokens
            if token
        ]

    frequencies = _dynamic_token_frequency(
        fields
    )

    field_count = max(
        len(fields),
        1
    )

    result = []

    for token in tokens:

        if not token:

            continue

        frequency = frequencies.get(
            token,
            0
        )

        relative_frequency = (
            frequency / field_count
        )

        if relative_frequency >= 0.45:

            continue

        result.append(
            token
        )

    return result


# ==========================================================
# SEMANTIC FIELD RESOLUTION
# ==========================================================

def _dynamic_find_semantic_field(
    fields: Dict[str, Dict[str, Any]],
    source_field: str,
    user_message: str = "",
) -> Optional[str]:

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

    source_lower = (
        source_field.lower()
    )

    # ======================================================
    # EXACT TECHNICAL FIELD
    # ======================================================

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
            source_tokens,
            fields=fields,
        )
    )

    request_informative_tokens = (
        _dynamic_non_generic_tokens(
            request_tokens,
            fields=fields,
        )
    )

    if not source_non_generic_tokens:

        print(
            "\n===== SEMANTIC FIELD REJECTED ====="
        )

        print(
            "SOURCE FIELD:",
            source_field
        )

        print(
            "REASON:",
            "source expression contains no informative semantic tokens"
        )

        return None

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
        ).strip()

        field_help = str(
            field_meta.get(
                "help",
                ""
            )
            or ""
        ).strip()

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

        # --------------------------------------------------
        # EVIDENZA DIRETTA DEL CAMPO
        #
        # Questa è la prova principale.
        #
        # relation_tokens NON vengono considerati sufficienti
        # da soli: una relazione come purchase.order.line non
        # significa che il campo rappresenti "purchase order".
        # --------------------------------------------------

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

        direct_source_overlap = (
            source_name_overlap
            .union(
                source_label_overlap
            )
            .union(
                source_help_overlap
            )
        )

        direct_source_count = len(
            direct_source_overlap
        )

        source_count = len(
            set(
                source_non_generic_tokens
            )
        )

        source_coverage = (
            direct_source_count / source_count
            if source_count > 0
            else 0.0
        )

        # --------------------------------------------------
        # Un concetto multi-token deve essere rappresentato
        # direttamente dal nome/label/help del campo.
        #
        # Esempio:
        # "purchase order"
        #
        # "order_line" -> order soltanto => REJECT
        #
        # "order reference"
        # con label "Order Reference" => ACCEPT
        # --------------------------------------------------

        if source_count >= 2:

            if direct_source_count < 2:

                continue

            if source_coverage < 0.75:

                continue

        else:

            # ------------------------------------------------
            # Per un concetto a singolo token basta una prova
            # diretta, ma non una prova derivata esclusivamente
            # dalla relazione.
            # ------------------------------------------------

            if direct_source_count == 0:

                continue

        request_name_overlap = (
            set(
                request_informative_tokens
            ).intersection(
                name_tokens
            )
        )

        request_label_overlap = (
            set(
                request_informative_tokens
            ).intersection(
                label_tokens
            )
        )

        request_help_overlap = (
            set(
                request_informative_tokens
            ).intersection(
                help_tokens
            )
        )

        request_relation_overlap = (
            set(
                request_informative_tokens
            ).intersection(
                relation_tokens
            )
        )

        request_evidence = bool(
            request_name_overlap
            or request_label_overlap
            or request_help_overlap
            or request_relation_overlap
        )

        # --------------------------------------------------
        # SCORE
        # --------------------------------------------------

        score = 0.0

        for token in source_name_overlap:

            score += 70.0

        for token in source_label_overlap:

            score += 60.0

        for token in source_help_overlap:

            score += 40.0

        # La relazione è una prova secondaria soltanto.
        for token in source_relation_overlap:

            score += 15.0

        for token in request_name_overlap:

            score += 10.0

        for token in request_label_overlap:

            score += 15.0

        for token in request_help_overlap:

            score += 8.0

        for token in request_relation_overlap:

            score += 5.0

        # --------------------------------------------------
        # Corrispondenze forti
        # --------------------------------------------------

        source_text = " ".join(
            source_non_generic_tokens
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

        if (
            source_text
            and source_text == name_text
        ):

            score += 150.0

        if (
            source_text
            and source_text == label_text
        ):

            score += 140.0

        if (
            source_text
            and source_text in label_text
        ):

            score += 90.0

        if (
            source_text
            and source_text in help_text
        ):

            score += 60.0

        # --------------------------------------------------
        # Molte evidenze dirette = maggiore affidabilità
        # --------------------------------------------------

        score += (
            direct_source_count
            * 35.0
        )

        score += (
            source_coverage
            * 80.0
        )

        # --------------------------------------------------
        # Tipo campo
        # --------------------------------------------------

        if field_type == "many2one":

            score += 20.0

        if field_meta.get(
            "store"
        ) is True:

            score += 10.0

        # --------------------------------------------------
        # Penalità tecniche generiche
        # --------------------------------------------------

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

            score -= 10.0

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

            score -= 25.0

        if score <= 0:

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

                "source_name_overlap":
                    source_name_overlap,

                "source_label_overlap":
                    source_label_overlap,

                "source_help_overlap":
                    source_help_overlap,

                "source_relation_overlap":
                    source_relation_overlap,

                "request_evidence":
                    request_evidence,

                "source_coverage":
                    source_coverage,

                "direct_source_count":
                    direct_source_count,

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
            "no field contains sufficient direct metadata evidence"
        )

        return None

    candidates.sort(
        key=lambda candidate: (
            -candidate["score"],
            -candidate["direct_source_count"],
            -candidate["source_coverage"],
            candidate["name"].lower(),
        )
    )

    best = candidates[0]

    best_score = float(
        best.get(
            "score",
            0.0
        )
    )

    second_score = 0.0

    if len(
        candidates
    ) > 1:

        second_score = float(
            candidates[1].get(
                "score",
                0.0
            )
        )

    minimum_score = 80.0
    margin_required = 15.0

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

    # ------------------------------------------------------
    # Se la corrispondenza non è sufficientemente distinta,
    # rifiutiamo invece di scegliere arbitrariamente.
    # ------------------------------------------------------

    if len(
        candidates
    ) > 1:

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
                "ambiguous metadata-backed semantic resolution"
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
        "DIRECT SOURCE TOKENS:",
        best.get(
            "direct_source_count"
        )
    )

    print(
        "SOURCE COVERAGE:",
        best.get(
            "source_coverage"
        )
    )

    print(
        "SCORE:",
        best_score
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

        possible_base, possible_suffix = (
            expression.split(
                ":",
                1
            )
        )

        possible_base = (
            possible_base.strip()
        )

        possible_suffix = (
            possible_suffix
            .strip()
            .lower()
        )

        if possible_suffix in (
            DYNAMIC_DATE_GRANULARITIES
            | {
                "sum",
                "avg",
                "min",
                "max",
                "count",
                "count_distinct",
            }
        ):

            base_expression = (
                possible_base
            )

            aggregate = (
                possible_suffix
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

    if aggregate:

        resolved = (
            f"{resolved_base}:{aggregate}"
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


DYNAMIC_ORDERING_TERMS = [
    "ordinato",
    "ordinati",
    "ordinata",
    "ordinate",
    "in ordine",
    "ordine crescente",
    "ordine decrescente",
    "crescente",
    "decrescente",
    "classifica",
    "top",
    "maggior",
    "maggiore",
    "massimo",
    "massimi",
    "massima",
    "massime",
    "piu",
    "più",
]


def _dynamic_user_requires_ordering(
    user_message: str
) -> bool:

    text = str(
        user_message or ""
    ).strip().lower()

    if not text:

        return False

    return any(
        phrase in text
        for phrase in DYNAMIC_ORDERING_TERMS
    )


def _dynamic_apply_resolved_field_mappings(
    params: Dict[str, Any],
    resolved_fields: Dict[str, str],
) -> Dict[str, Any]:

    if not isinstance(
        params,
        dict
    ):
        return params

    if not isinstance(
        resolved_fields,
        dict
    ) or not resolved_fields:

        return params

    normalized_mapping = {}

    for source, target in resolved_fields.items():

        if not isinstance(
            source,
            str
        ):
            continue

        if not isinstance(
            target,
            str
        ):
            continue

        source = source.strip()
        target = target.strip()

        if (
            not source
            or not target
            or source == target
        ):
            continue

        normalized_mapping[source] = target

    if not normalized_mapping:

        return params

    def resolve_expression(
        expression: Any
    ) -> Any:

        if not isinstance(
            expression,
            str
        ):

            return expression

        original = expression.strip()

        if not original:

            return expression

        base = _dynamic_expression_base(
            original
        )

        if not base:

            return expression

        target = normalized_mapping.get(
            base
        )

        if not target:

            return expression

        if original == base:

            return target

        suffix = original[
            len(base):
        ]

        return (
            f"{target}{suffix}"
        )

    fields = params.get(
        "fields"
    )

    if isinstance(
        fields,
        list
    ):

        params["fields"] = [

            resolve_expression(
                value
            )

            for value in fields

            if isinstance(
                value,
                str
            )

        ]

    elif isinstance(
        fields,
        str
    ):

        params["fields"] = [
            resolve_expression(
                fields
            )
        ]

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

        params["groupby"] = [

            resolve_expression(
                value
            )

            for value in groupby

            if isinstance(
                value,
                str
            )

        ]

    orderby = params.get(
        "orderby"
    )

    if isinstance(
        orderby,
        str
    ):

        order_parts = (
            orderby.strip().split()
        )

        if order_parts:

            resolved_order_field = (
                resolve_expression(
                    order_parts[0]
                )
            )

            direction = (
                order_parts[1]
                if len(order_parts) > 1
                else "asc"
            )

            params["orderby"] = (
                f"{resolved_order_field} "
                f"{direction}"
            )

    domain = params.get(
        "domain"
    )

    if isinstance(
        domain,
        list
    ):

        repaired_domain = []

        for item in domain:

            if (
                isinstance(
                    item,
                    list
                )
                and len(item) == 3
                and isinstance(
                    item[0],
                    str
                )
            ):

                translated_item = list(
                    item
                )

                field = (
                    translated_item[0]
                )

                root_field = field.split(
                    ".",
                    1
                )[0]

                replacement = (
                    normalized_mapping.get(
                        root_field
                    )
                )

                if replacement:

                    if "." in field:

                        nested_tail = field.split(
                            ".",
                            1
                        )[1]

                        translated_item[0] = (
                            f"{replacement}."
                            f"{nested_tail}"
                        )

                    else:

                        translated_item[0] = (
                            replacement
                        )

                repaired_domain.append(
                    translated_item
                )

            else:

                repaired_domain.append(
                    item
                )

        params["domain"] = repaired_domain

    print(
        "\n===== RESOLVED FIELD MAPPINGS APPLIED ====="
    )

    print(
        "MAPPINGS:",
        normalized_mapping
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

    return params


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

        params["groupby"] = [

            original_groupby.strip()

        ]

        params["groupby"] = [

            value

            for value in params["groupby"]

            if value

        ]

    elif (
        original_groupby is not None
        and not isinstance(
            original_groupby,
            list
        )
    ):

        raise ValueError(
            "Il groupby fornito dal planner non è valido."
        )

    original_fields = params.get(
        "fields"
    )

    if (
        isinstance(
            original_fields,
            list
        )
        and original_fields
    ):

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

        else:

            raise ValueError(
                "Nessun campo richiesto dal planner "
                "è stato risolto sui metadati Odoo reali."
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

        if not resolved_fields:

            raise ValueError(
                "Il campo richiesto dal planner "
                "non è stato risolto sui metadati Odoo reali."
            )

        params["fields"] = (
            resolved_fields
        )

    groupby_values = params.get(
        "groupby"
    )

    if (
        isinstance(
            groupby_values,
            list
        )
        and groupby_values
    ):

        resolved_groupby = (
            _dynamic_resolve_groupby(
                values=groupby_values,
                fields=fields,
                user_message=user_message,
            )
        )

        if (
            len(
                resolved_groupby
            )
            != len(
                groupby_values
            )
        ):

            print(
                "\n===== DYNAMIC GROUPBY RESOLUTION FAILED ====="
            )

            print(
                "ORIGINAL:",
                groupby_values
            )

            print(
                "RESOLVED:",
                resolved_groupby
            )

            raise ValueError(
                "Il groupby richiesto dal planner "
                "non è stato completamente risolto "
                "sui metadati Odoo reali."
            )

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

    original_orderby = params.get(
        "orderby"
    )

    if original_orderby:

        resolved_orderby = (
            _dynamic_resolve_orderby(
                orderby=original_orderby,
                fields=fields,
                user_message=user_message,
            )
        )

        if resolved_orderby:

            if resolved_orderby != original_orderby:

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

        else:

            if _dynamic_user_requires_ordering(
                user_message
            ):

                raise ValueError(
                    "L'ordinamento richiesto dall'utente "
                    "non è stato risolto su un campo Odoo reale."
                )

            print(
                "\n===== DYNAMIC ORDERBY REMOVED ====="
            )

            print(
                "UNRESOLVED ORDERBY:",
                original_orderby
            )

            print(
                "REASON:",
                "ordering not independently required by user intent"
            )

            params.pop(
                "orderby",
                None
            )

    return params


def _dynamic_apply_field_resolution(
    params: Dict[str, Any],
    fields: Dict[str, Dict[str, Any]],
    user_message: str,
    semantic_concepts: Optional[
        List[Dict[str, Any]]
    ] = None,
    tree_view: Optional[Dict[str, Any]] = None,
    prefer_tree_view: bool = False,
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

    # ======================================================
    # TREE VIEW PRIORITY
    #
    # Per search_read la tree/list view reale Odoo è la
    # fonte autorevole della presentazione standard.
    #
    # Questo evita che il Planner scelga arbitrariamente
    # colonne human-facing.
    # ======================================================

    if (
        prefer_tree_view
        and isinstance(
            tree_view,
            dict
        )
    ):

        dynamic_fields = (
            _dynamic_default_fields(
                fields=fields,

                limit=8,

                user_message=user_message,

                semantic_concepts=(
                    semantic_concepts
                    or []
                ),

                groupby=params.get(
                    "groupby",
                    []
                ),

                orderby=params.get(
                    "orderby"
                ),

                tree_view=tree_view,
            )
        )

        if dynamic_fields:

            params["fields"] = (
                dynamic_fields
            )

            print(
                "\n===== ODOO TREE VIEW PRESENTATION PRIORITY ====="
            )

            print(
                "PRESENTATION SOURCE:",
                "ODOO TREE VIEW"
            )

            print(
                "FIELDS:",
                dynamic_fields
            )

    elif (
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

                user_message=user_message,

                semantic_concepts=(
                    semantic_concepts
                    or []
                ),

                groupby=params.get(
                    "groupby",
                    []
                ),

                orderby=params.get(
                    "orderby"
                ),

                tree_view=tree_view,
            )
        )

        if dynamic_fields:

            params["fields"] = (
                dynamic_fields
            )

            print(
                "\n===== DYNAMIC HUMAN FIELD RESOLUTION ====="
            )

            print(
                "AUTO HUMAN FIELDS:",
                dynamic_fields
            )

            print(
                "USER MESSAGE:",
                user_message
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

    params = (
        _dynamic_apply_parameter_field_resolution(
            params=params,

            fields=fields,

            user_message=user_message,
        )
    )

    return params

def _dynamic_remove_invalid_fields(
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
                    user_message=user_message,
                )
            )

            if resolved:

                valid_fields.append(
                    resolved
                )

        if (
            requested_fields
            and not valid_fields
        ):

            raise ValueError(
                "Tutti i campi richiesti "
                "sono risultati incompatibili con i metadati Odoo reali."
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
                    user_message=user_message,
                )
            )

            if resolved:

                valid_groupby.append(
                    resolved
                )

        if (
            requested_groupby
            and len(valid_groupby)
            != len(requested_groupby)
        ):

            raise ValueError(
                "Il groupby contiene almeno un campo "
                "non risolvibile sui metadati Odoo reali."
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

    # ------------------------------------------------------
    # Una relazione annidata proposta dal planner non viene
    # trasformata arbitrariamente.
    #
    # Se il root field viene risolto semanticamente, usiamo
    # il campo reale come root della condizione.
    # ------------------------------------------------------

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

        suffix = (
            suffix
            .strip()
            .lower()
        )

        if suffix in (
            DYNAMIC_DATE_GRANULARITIES
            | {
                "sum",
                "avg",
                "min",
                "max",
                "count",
                "count_distinct",
            }
        ):

            return first.strip()

    return text

def _dynamic_expression_granularity(
    expression: Any,
) -> Optional[str]:

    if not isinstance(
        expression,
        str,
    ):

        return None

    text = expression.strip()

    if ":" not in text:

        return None

    _base, suffix = (
        text.split(
            ":",
            1
        )
    )

    suffix = (
        suffix
        .strip()
        .lower()
    )

    if suffix in DYNAMIC_DATE_GRANULARITIES:

        return suffix

    return None

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

        if (
            not isinstance(
                current_fields,
                list
            )
            or not current_fields
        ):

            params["fields"] = list(
                source_fields
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

        if (
            not isinstance(
                current_groupby,
                list
            )
            or not current_groupby
        ):

            params["groupby"] = list(
                source_groupby
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


def _dynamic_model_resolution_score(
    params: Dict[str, Any],
    fields: Dict[str, Dict[str, Any]],
    semantic_concepts: List[Dict[str, Any]],
    resolved_fields: Dict[str, str],
) -> float:

    if not isinstance(
        fields,
        dict
    ):

        return 0.0

    if not isinstance(
        resolved_fields,
        dict
    ):

        return 0.0

    score = 0.0

    groupby = params.get(
        "groupby",
        []
    )

    if isinstance(
        groupby,
        str
    ):

        groupby = [
            groupby
        ]

    groupby_bases = set()

    if isinstance(
        groupby,
        list
    ):

        for expression in groupby:

            base = _dynamic_expression_base(
                expression
            )

            if base:

                groupby_bases.add(
                    base
                )

    for source_field, resolved_field in (
        resolved_fields.items()
    ):

        if not isinstance(
            source_field,
            str
        ):

            continue

        if not isinstance(
            resolved_field,
            str
        ):

            continue

        resolved_meta = fields.get(
            resolved_field,
            {}
        )

        if not isinstance(
            resolved_meta,
            dict
        ):

            resolved_meta = {}

        source_tokens = set(
            _normalize_semantic_tokens(
                source_field
            )
        )

        field_tokens = set(
            _normalize_semantic_tokens(
                resolved_field
            )
        )

        label_tokens = set(
            _normalize_semantic_tokens(
                resolved_meta.get(
                    "string",
                    resolved_meta.get(
                        "field_description",
                        ""
                    )
                )
            )
        )

        help_tokens = set(
            _normalize_semantic_tokens(
                resolved_meta.get(
                    "help",
                    ""
                )
            )
        )

        relation_tokens = set(
            _normalize_semantic_tokens(
                resolved_meta.get(
                    "relation",
                    ""
                )
            )
        )

        if (
            source_field
            == resolved_field
        ):

            score += 35.0

        score += (
            len(
                source_tokens.intersection(
                    field_tokens
                )
            )
            * 20.0
        )

        score += (
            len(
                source_tokens.intersection(
                    label_tokens
                )
            )
            * 35.0
        )

        score += (
            len(
                source_tokens.intersection(
                    help_tokens
                )
            )
            * 15.0
        )

        score += (
            len(
                source_tokens.intersection(
                    relation_tokens
                )
            )
            * 25.0
        )

        field_type = str(
            resolved_meta.get(
                "type",
                resolved_meta.get(
                    "ttype",
                    ""
                )
            )
            or ""
        ).lower()

        if field_type == "many2one":

            score += 20.0

        if resolved_field in groupby_bases:

            score += 100.0

    covered_concepts = 0

    for concept_entry in semantic_concepts:

        if not isinstance(
            concept_entry,
            dict
        ):

            continue

        concept = concept_entry.get(
            "concept"
        )

        aliases = concept_entry.get(
            "queries",
            []
        )

        if not isinstance(
            concept,
            str
        ):

            continue

        candidate_aliases = []

        if isinstance(
            aliases,
            list
        ):

            candidate_aliases.extend(
                alias
                for alias in aliases
                if isinstance(
                    alias,
                    str
                )
            )

        candidate_aliases.append(
            concept
        )

        concept_covered = False

        for alias in candidate_aliases:

            alias = alias.strip()

            if not alias:

                continue

            alias_tokens = set(
                _normalize_semantic_tokens(
                    alias
                )
            )

            for resolved_field in resolved_fields.values():

                resolved_meta = fields.get(
                    resolved_field,
                    {}
                )

                if not isinstance(
                    resolved_meta,
                    dict
                ):

                    continue

                evidence_tokens = set(
                    _normalize_semantic_tokens(
                        " ".join(
                            [
                                resolved_field,

                                str(
                                    resolved_meta.get(
                                        "string",
                                        ""
                                    )
                                    or ""
                                ),

                                str(
                                    resolved_meta.get(
                                        "help",
                                        ""
                                    )
                                    or ""
                                ),

                                str(
                                    resolved_meta.get(
                                        "relation",
                                        ""
                                    )
                                    or ""
                                ),

                            ]
                        )
                    )
                )

                if alias_tokens.intersection(
                    evidence_tokens
                ):

                    concept_covered = True

                    break

            if concept_covered:

                break

        if concept_covered:

            covered_concepts += 1

    score += (
        covered_concepts
        * 120.0
    )

    return score


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
        request_tokens.intersection(
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
            current_tokens.intersection(
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

        "report":
            -8.0,

        "wizard":
            -12.0,

        "transient":
            -10.0,

        "line":
            -2.0,

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


# ==========================================================
# SEMANTIC CONCEPT COMPATIBILITY
# ==========================================================

def _dynamic_normalize_semantic_concepts(
    semantic_concepts: Any
) -> List[Dict[str, Any]]:

    if not isinstance(
        semantic_concepts,
        list
    ):

        return []

    result = []

    seen = set()

    for entry in semantic_concepts:

        if isinstance(
            entry,
            str
        ):

            concept = entry.strip()

            aliases = []

        elif isinstance(
            entry,
            dict
        ):

            concept = entry.get(
                "concept"
            )

            aliases = entry.get(
                "queries",
                []
            )

            if not isinstance(
                aliases,
                list
            ):

                aliases = []

        else:

            continue

        if not isinstance(
            concept,
            str
        ):

            continue

        concept = concept.strip()

        if not concept:

            continue

        concept_key = (
            " ".join(
                _normalize_semantic_tokens(
                    concept
                )
            )
        )

        if not concept_key:

            continue

        if concept_key in seen:

            continue

        normalized_aliases = []

        alias_seen = set()

        for alias in aliases:

            if not isinstance(
                alias,
                str
            ):

                continue

            alias = alias.strip()

            if not alias:

                continue

            alias_key = (
                " ".join(
                    _normalize_semantic_tokens(
                        alias
                    )
                )
            )

            if (
                not alias_key
                or alias_key in alias_seen
            ):

                continue

            alias_seen.add(
                alias_key
            )

            normalized_aliases.append(
                alias
            )

        if not normalized_aliases:

            normalized_aliases = [
                concept
            ]

        result.append(
            {
                "concept":
                    concept,

                "queries":
                    normalized_aliases[:8],
            }
        )

        seen.add(
            concept_key
        )

    return result[:8]


def _dynamic_semantic_concept_coverage(
    fields: Dict[str, Dict[str, Any]],
    semantic_concepts: List[Dict[str, Any]],
    user_message: str = "",
    model: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[
    bool,
    Dict[str, Any]
]:

    semantic_concepts = (
        _dynamic_normalize_semantic_concepts(
            semantic_concepts
        )
    )

    if not semantic_concepts:

        return (
            True,
            {
                "required_concepts": [],
                "covered_concepts": [],
                "missing_concepts": [],
                "context_only_concepts": [],
                "resolved": {},
            }
        )

    if not isinstance(
        fields,
        dict
    ) or not fields:

        return (
            True,
            {
                "required_concepts":
                    [],

                "covered_concepts":
                    [],

                "missing_concepts":
                    [],

                "context_only_concepts":
                    [
                        entry.get(
                            "concept"
                        )
                        for entry in semantic_concepts
                    ],

                "resolved":
                    {},
            }
        )

    if not isinstance(
        metadata,
        dict
    ):

        metadata = {}

    # ======================================================
    # IDENTITÀ DEL MODELLO
    #
    # Un concetto multi-token che coincide fortemente con
    # l'identità del modello rappresenta l'entità richiesta,
    # NON un campo da selezionare.
    #
    # Questo evita casi come:
    #
    #   "purchase order" -> "date_order"
    #
    # perché "Purchase Order" identifica il modello stesso,
    # mentre "Order Date" identifica un attributo.
    #
    # Nessun modello o campo Odoo è hardcodificato.
    # ======================================================

    model_identity_text = _dynamic_model_context_text(
        model=model,
        metadata=metadata,
    )

    model_identity_tokens = set(
        _normalize_semantic_tokens(
            model_identity_text
        )
    )

    model_name_tokens = set(
        _normalize_semantic_tokens(
            model
        )
    )

    if not model_identity_tokens:

        model_identity_tokens = (
            model_name_tokens
        )

    covered_concepts = []
    missing_concepts = []
    context_only_concepts = []
    resolved = {}

    used_fields = set()

    for concept_entry in semantic_concepts:

        concept = concept_entry.get(
            "concept"
        )

        aliases = concept_entry.get(
            "queries",
            []
        )

        if not isinstance(
            concept,
            str
        ):

            continue

        concept = concept.strip()

        if not concept:

            continue

        if not isinstance(
            aliases,
            list
        ):

            aliases = []

        normalized_aliases = [

            alias.strip()

            for alias in aliases

            if isinstance(
                alias,
                str
            )
            and alias.strip()

        ]

        if not normalized_aliases:

            normalized_aliases = [
                concept
            ]

        # ==================================================
        # MODEL ENTITY CHECK
        # ==================================================

        entity_alias = None
        entity_alias_score = 0.0
        entity_alias_coverage = 0.0

        for alias in normalized_aliases:

            alias_tokens = set(
                _normalize_semantic_tokens(
                    alias
                )
            )

            if len(alias_tokens) < 2:

                continue

            informative_alias_tokens = (
                _dynamic_non_generic_tokens(
                    list(alias_tokens),
                    fields=fields,
                )
            )

            informative_alias_set = set(
                informative_alias_tokens
            )

            if not informative_alias_set:

                continue

            model_overlap = (
                informative_alias_set.intersection(
                    model_identity_tokens
                )
            )

            model_name_overlap = (
                informative_alias_set.intersection(
                    model_name_tokens
                )
            )

            direct_overlap = (
                model_overlap
                or model_name_overlap
            )

            coverage = (
                len(direct_overlap)
                / len(informative_alias_set)
                if informative_alias_set
                else 0.0
            )

            score = (
                len(direct_overlap) * 40.0
                + coverage * 100.0
            )

            if (
                coverage >= 0.75
                and (
                    len(direct_overlap) >= 2
                )
            ):

                if score > entity_alias_score:

                    entity_alias = alias

                    entity_alias_score = score

                    entity_alias_coverage = coverage

        if entity_alias:

            context_only_concepts.append(
                concept
            )

            print(
                "\n===== SEMANTIC CONCEPT KEPT AS ENTITY CONTEXT ====="
            )

            print(
                "CONCEPT:",
                concept
            )

            print(
                "ENTITY ALIAS:",
                entity_alias
            )

            print(
                "MODEL:",
                model
            )

            print(
                "MODEL IDENTITY:",
                model_identity_text
            )

            print(
                "ENTITY COVERAGE:",
                entity_alias_coverage
            )

            print(
                "REASON:",
                "concept strongly matches model identity; "
                "it is an entity/model concept, not a field"
            )

            continue

        # ==================================================
        # FIELD RESOLUTION
        # ==================================================

        concept_candidates = []

        for alias in normalized_aliases:

            candidate = (
                _dynamic_find_semantic_field(
                    fields=fields,
                    source_field=alias,
                    user_message=user_message,
                )
            )

            if not candidate:

                continue

            if candidate in used_fields:

                continue

            candidate_meta = fields.get(
                candidate,
                {}
            )

            if not isinstance(
                candidate_meta,
                dict
            ):

                candidate_meta = {}

            alias_tokens = set(
                _normalize_semantic_tokens(
                    alias
                )
            )

            field_metadata_text = " ".join(
                [
                    candidate,

                    str(
                        candidate_meta.get(
                            "string",
                            candidate_meta.get(
                                "field_description",
                                ""
                            )
                        )
                        or ""
                    ),

                    str(
                        candidate_meta.get(
                            "help",
                            ""
                        )
                        or ""
                    ),

                    str(
                        candidate_meta.get(
                            "relation",
                            ""
                        )
                        or ""
                    ),
                ]
            )

            metadata_tokens = set(
                _normalize_semantic_tokens(
                    field_metadata_text
                )
            )

            evidence = len(
                alias_tokens.intersection(
                    metadata_tokens
                )
            )

            direct_name = (
                alias.lower()
                == candidate.lower()
            )

            candidate_score = (
                evidence * 25.0
                + (
                    50.0
                    if direct_name
                    else 0.0
                )
            )

            field_type = str(
                candidate_meta.get(
                    "type",
                    candidate_meta.get(
                        "ttype",
                        ""
                    )
                )
                or ""
            ).lower()

            if field_type == "many2one":

                candidate_score += 15.0

            concept_candidates.append(
                (
                    candidate_score,
                    candidate,
                )
            )

        if concept_candidates:

            concept_candidates.sort(
                key=lambda item: (
                    -item[0],
                    item[1].lower(),
                )
            )

            best_candidate = (
                concept_candidates[0][1]
            )

            covered_concepts.append(
                concept
            )

            resolved[
                concept
            ] = {

                "field":
                    best_candidate,

                "aliases":
                    normalized_aliases,

            }

            used_fields.add(
                best_candidate
            )

            continue

        # ==================================================
        # CONTEXT ONLY
        # ==================================================

        context_only_concepts.append(
            concept
        )

        print(
            "\n===== SEMANTIC CONCEPT KEPT AS CONTEXT ====="
        )

        print(
            "CONCEPT:",
            concept
        )

        print(
            "REASON:",
            "no sufficient metadata-backed field evidence; "
            "treated as entity/context concept"
        )

    compatible = True

    return (
        compatible,
        {

            "required_concepts":
                covered_concepts,

            "covered_concepts":
                covered_concepts,

            "missing_concepts":
                missing_concepts,

            "context_only_concepts":
                context_only_concepts,

            "resolved":
                resolved,

        }
    )

def _dynamic_groupby_semantically_compatible(
    params: Dict[str, Any],
    fields: Dict[str, Dict[str, Any]],
    semantic_concepts: List[Dict[str, Any]],
    user_message: str = "",
) -> Tuple[
    bool,
    Dict[str, str]
]:

    if not isinstance(
        params,
        dict
    ):

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

    semantic_concepts = (
        _dynamic_normalize_semantic_concepts(
            semantic_concepts
        )
    )

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

    if not isinstance(
        groupby,
        list
    ) or not groupby:

        return (
            True,
            {}
        )

    resolved = {}

    for expression in groupby:

        if not isinstance(
            expression,
            str
        ):

            return (
                False,
                {}
            )

        expression = expression.strip()

        if not expression:

            return (
                False,
                {}
            )

        base = _dynamic_expression_base(
            expression
        )

        if not base:

            return (
                False,
                {}
            )

        # ==================================================
        # EXACT TECHNICAL FIELD
        # ==================================================

        if base in fields:

            field_meta = fields.get(
                base,
                {}
            )

            if not isinstance(
                field_meta,
                dict,
            ):

                field_meta = {}

            field_type = str(
                field_meta.get(
                    "type",
                    field_meta.get(
                        "ttype",
                        ""
                    )
                )
                or ""
            ).strip().lower()

            granularity = (
                _dynamic_expression_granularity(
                    expression
                )
            )

            # ==================================================
            # TEMPORAL GRANULARITY
            #
            # date_order:month
            # date_order:week
            # date_order:day
            # ...
            #
            # La granularità non è un campo Odoo separato.
            # È un'operazione applicata a un campo date/datetime
            # reale.
            # ==================================================

            if granularity:

                if field_type not in {
                    "date",
                    "datetime",
                }:

                    print(
                        "\n===== GROUPBY TEMPORAL GRANULARITY REJECTED ====="
                    )

                    print(
                        "GROUPBY:",
                        expression
                    )

                    print(
                        "BASE FIELD:",
                        base
                    )

                    print(
                        "FIELD TYPE:",
                        field_type
                    )

                    print(
                        "GRANULARITY:",
                        granularity
                    )

                    print(
                        "REASON:",
                        "temporal granularity requires a date/datetime field"
                    )

                    return (
                        False,
                        {}
                    )

                print(
                    "\n===== GROUPBY TEMPORAL GRANULARITY ACCEPTED ====="
                )

                print(
                    "GROUPBY:",
                    expression
                )

                print(
                    "BASE FIELD:",
                    base
                )

                print(
                    "FIELD TYPE:",
                    field_type
                )

                print(
                    "GRANULARITY:",
                    granularity
                )

                resolved[
                    expression
                ] = expression

                continue

            # ==================================================
            # NORMALE DIMENSIONE
            # ==================================================

            if semantic_concepts:

                compatible_exact = False

                for concept_entry in semantic_concepts:

                    if not isinstance(
                        concept_entry,
                        dict
                    ):

                        continue

                    concept = concept_entry.get(
                        "concept"
                    )

                    aliases = concept_entry.get(
                        "queries",
                        []
                    )

                    if not isinstance(
                        concept,
                        str
                    ):

                        continue

                    candidate_aliases = []

                    if isinstance(
                        aliases,
                        list
                    ):

                        candidate_aliases.extend(
                            alias
                            for alias in aliases
                            if isinstance(
                                alias,
                                str
                            )
                        )

                    candidate_aliases.append(
                        concept
                    )

                    for alias in candidate_aliases:

                        semantic_field = (
                            _dynamic_find_semantic_field(
                                fields=fields,
                                source_field=alias,
                                user_message=user_message,
                            )
                        )

                        if semantic_field == base:

                            compatible_exact = True

                            break

                    if compatible_exact:

                        break

                if not compatible_exact:

                    print(
                        "\n===== GROUPBY SEMANTIC CHECK FAILED ====="
                    )

                    print(
                        "GROUPBY:",
                        expression
                    )

                    print(
                        "REASON:",
                        "technical field exists but is not supported by semantic request evidence"
                    )

                    return (
                        False,
                        {}
                    )

            resolved[
                expression
            ] = base

            print(
                "\n===== GROUPBY SEMANTIC CHECK PASSED ====="
            )

            print(
                "GROUPBY:",
                expression
            )

            print(
                "RESOLVED FIELD:",
                base
            )

            continue

        # ==================================================
        # INVALID TECHNICAL HINT
        # ==================================================
        #
        # Il planner può aver proposto un technical name
        # inesistente. NON lo trattiamo come errore definitivo.
        #
        # Usiamo invece i concetti semantici e i metadata reali.
        # ==================================================

        semantic_candidates = []

        direct_resolution = (
            _dynamic_find_semantic_field(
                fields=fields,
                source_field=base,
                user_message=user_message,
            )
        )

        if direct_resolution:

            semantic_candidates.append(
                (
                    0.0,
                    direct_resolution,
                    "technical_hint",
                )
            )

        for concept_entry in semantic_concepts:

            concept = concept_entry.get(
                "concept"
            )

            aliases = concept_entry.get(
                "queries",
                []
            )

            if not isinstance(
                concept,
                str
            ):

                continue

            candidate_aliases = []

            if isinstance(
                aliases,
                list
            ):

                candidate_aliases.extend(
                    alias
                    for alias in aliases
                    if isinstance(
                        alias,
                        str
                    )
                )

            candidate_aliases.append(
                concept
            )

            for alias in candidate_aliases:

                semantic_field = (
                    _dynamic_find_semantic_field(
                        fields=fields,
                        source_field=alias,
                        user_message=user_message,
                    )
                )

                if not semantic_field:

                    continue

                candidate_meta = fields.get(
                    semantic_field,
                    {}
                )

                if not isinstance(
                    candidate_meta,
                    dict
                ):

                    candidate_meta = {}

                field_label = str(
                    candidate_meta.get(
                        "string",
                        candidate_meta.get(
                            "field_description",
                            ""
                        )
                    )
                    or ""
                )

                field_help = str(
                    candidate_meta.get(
                        "help",
                        ""
                    )
                    or ""
                )

                relation = str(
                    candidate_meta.get(
                        "relation",
                        ""
                    )
                    or ""
                )

                source_tokens = set(
                    _normalize_semantic_tokens(
                        base
                    )
                )

                alias_tokens = set(
                    _normalize_semantic_tokens(
                        alias
                    )
                )

                candidate_metadata_tokens = set(
                    _normalize_semantic_tokens(
                        " ".join(
                            [
                                semantic_field,
                                field_label,
                                field_help,
                                relation,
                            ]
                        )
                    )
                )

                request_tokens = set(
                    _dynamic_non_generic_tokens(
                        _normalize_semantic_tokens(
                            user_message
                        ),
                        fields=fields,
                    )
                )

                source_overlap = len(
                    source_tokens.intersection(
                        candidate_metadata_tokens
                    )
                )

                alias_overlap = len(
                    alias_tokens.intersection(
                        candidate_metadata_tokens
                    )
                )

                request_overlap = len(
                    request_tokens.intersection(
                        candidate_metadata_tokens
                    )
                )

                field_score = (
                    source_overlap * 40.0
                    + alias_overlap * 65.0
                    + request_overlap * 25.0
                )

                if (
                    candidate_meta.get(
                        "ttype",
                        candidate_meta.get(
                            "type",
                            ""
                        )
                    )
                    == "many2one"
                ):

                    field_score += 15.0

                semantic_candidates.append(
                    (
                        field_score,
                        semantic_field,
                        concept,
                    )
                )

        if not semantic_candidates:

            print(
                "\n===== GROUPBY SEMANTIC CHECK FAILED ====="
            )

            print(
                "GROUPBY:",
                expression
            )

            print(
                "REASON:",
                "technical hint does not exist and no metadata-backed semantic replacement was found"
            )

            return (
                False,
                {}
            )

        semantic_candidates.sort(
            key=lambda item: (
                -item[0],
                item[1].lower(),
            )
        )

        best_score, best_field, best_concept = (
            semantic_candidates[0]
        )

        second_score = (
            semantic_candidates[1][0]
            if len(semantic_candidates) > 1
            else 0.0
        )

        if (
            len(semantic_candidates) > 1
            and best_score <= 0
        ):

            print(
                "\n===== GROUPBY SEMANTIC CHECK FAILED ====="
            )

            print(
                "GROUPBY:",
                expression
            )

            print(
                "REASON:",
                "no positive metadata-backed semantic evidence"
            )

            return (
                False,
                {}
            )

        if (
            len(semantic_candidates) > 1
            and best_score > 0
            and (
                best_score
                - second_score
                < 10.0
            )
        ):

            print(
                "\n===== GROUPBY SEMANTIC CHECK FAILED ====="
            )

            print(
                "GROUPBY:",
                expression
            )

            print(
                "BEST FIELD:",
                best_field
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
                "REASON:",
                "ambiguous metadata-backed semantic groupby resolution"
            )

            return (
                False,
                {}
            )

        resolved[
            expression
        ] = best_field

        print(
            "\n===== GROUPBY SEMANTIC CHECK PASSED ====="
        )

        print(
            "GROUPBY:",
            expression
        )

        print(
            "INVALID TECHNICAL HINT:",
            base
        )

        print(
            "RESOLVED FIELD:",
            best_field
        )

        print(
            "CONCEPT:",
            best_concept
        )

        print(
            "RESOLUTION SCORE:",
            best_score
        )

    return (
        True,
        resolved
    )


# ==========================================================
# REQUIRED FIELD COMPATIBILITY
# ==========================================================

def _dynamic_required_fields_compatible(
    params: Dict[str, Any],
    fields: Dict[str, Dict[str, Any]],
    user_message: str,
    semantic_concepts: Optional[
        List[Dict[str, Any]]
    ] = None,
    model: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[
    bool,
    Dict[str, str]
]:

    if semantic_concepts is None:

        semantic_concepts = []

    semantic_concepts = (
        _dynamic_normalize_semantic_concepts(
            semantic_concepts
        )
    )

    # ======================================================
    # GROUPBY COMPATIBILITY
    # ======================================================

    groupby_compatibility = (
        _dynamic_groupby_semantically_compatible(
            params=params,
            fields=fields,
            semantic_concepts=semantic_concepts,
            user_message=user_message,
        )
    )

    if not groupby_compatibility[0]:

        print(
            "\n===== DYNAMIC MODEL COMPATIBILITY FAILED ====="
        )

        print(
            "REASON:",
            "groupby is not compatible with real Odoo metadata"
        )

        return (
            False,
            {}
        )

    resolved_fields: Dict[
        str,
        str
    ] = {}

    resolved_fields.update(
        groupby_compatibility[1]
    )

    # ======================================================
    # REQUIRED SEMANTIC CONCEPTS
    # ======================================================

    semantic_compatibility = (
        _dynamic_semantic_concept_coverage(
            fields=fields,
            semantic_concepts=semantic_concepts,
            user_message=user_message,
            model=model,
            metadata=metadata,
        )
    )

    if not semantic_compatibility[0]:

        print(
            "\n===== SEMANTIC CONCEPT COMPATIBILITY FAILED ====="
        )

        print(
            "REQUIRED CONCEPTS:",
            semantic_compatibility[1].get(
                "required_concepts",
                []
            )
        )

        print(
            "COVERED CONCEPTS:",
            semantic_compatibility[1].get(
                "covered_concepts",
                []
            )
        )

        print(
            "MISSING CONCEPTS:",
            semantic_compatibility[1].get(
                "missing_concepts",
                []
            )
        )

        return (
            False,
            {}
        )

    semantic_resolved = (
        semantic_compatibility[1].get(
            "resolved",
            {}
        )
    )

    if isinstance(
        semantic_resolved,
        dict
    ):

        for concept, data in semantic_resolved.items():

            if not isinstance(
                data,
                dict
            ):

                continue

            resolved_field = data.get(
                "field"
            )

            aliases = data.get(
                "aliases",
                []
            )

            if (
                not isinstance(
                    resolved_field,
                    str
                )
                or not resolved_field
            ):

                continue

            source_key = (
                aliases[0].strip()
                if (
                    isinstance(
                        aliases,
                        list
                    )
                    and aliases
                    and isinstance(
                        aliases[0],
                        str
                    )
                )
                else concept.strip()
            )

            if source_key:

                resolved_fields.setdefault(
                    source_key,
                    resolved_field
                )

            # Conserviamo anche il concept canonicalizzato
            # come risoluzione disponibile.
            if concept:

                resolved_fields.setdefault(
                    concept,
                    resolved_field
                )

    # ======================================================
    # TECHNICAL HINTS
    # ======================================================

    required_fields = (
        _dynamic_parameter_root_fields(
            params
        )
    )

    # ------------------------------------------------------
    # I technical hints non sono più "required" per definizione.
    #
    # Per essere considerati compatibili devono:
    #   - esistere realmente;
    #   - oppure poter essere risolti semanticamente;
    #   - e non contraddire la compatibilità complessiva.
    # ------------------------------------------------------

    filtered_required_fields = []

    for field in required_fields:

        tokens = _normalize_semantic_tokens(
            field
        )

        non_generic_tokens = (
            _dynamic_non_generic_tokens(
                tokens,
                fields=fields,
            )
        )

        if semantic_concepts and not non_generic_tokens:

            print(
                "\n===== GENERIC TECHNICAL HINT IGNORED ====="
            )

            print(
                "FIELD:",
                field
            )

            continue

        filtered_required_fields.append(
            field
        )

    required_fields = (
        filtered_required_fields
    )

    # ======================================================
    # RISOLUZIONE DEI TECHNICAL HINTS
    # ======================================================

    for source_field in required_fields:

        source_field = str(
            source_field or ""
        ).strip()

        if not source_field:

            continue

        # --------------------------------------------------
        # Già risolto semanticamente
        # --------------------------------------------------

        resolved = resolved_fields.get(
            source_field
        )

        if resolved:

            print(
                "FIELD COMPATIBLE:",
                source_field,
                "->",
                resolved,
                "| semantic resolution already available"
            )

            continue

        # --------------------------------------------------
        # Exact technical field
        # --------------------------------------------------

        if source_field in fields:

            resolved_fields[
                source_field
            ] = source_field

            print(
                "FIELD COMPATIBLE:",
                source_field,
                "->",
                source_field,
                "| exact technical match"
            )

            continue

        # --------------------------------------------------
        # Technical hint inesistente:
        # risoluzione metadata-backed.
        # --------------------------------------------------

        resolved = (
            _dynamic_find_semantic_field(
                fields=fields,
                source_field=source_field,
                user_message=user_message,
            )
        )

        if not resolved:

            print(
                "\n===== DYNAMIC TECHNICAL HINT UNRESOLVED ====="
            )

            print(
                "FIELD:",
                source_field
            )

            print(
                "REASON:",
                "planner technical hint could not be resolved against real metadata"
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
            "| metadata-backed semantic resolution"
        )

    # ======================================================
    # RISULTATO
    # ======================================================

    if not semantic_concepts and not required_fields:

        print(
            "\n===== DYNAMIC MODEL COMPATIBILITY PASSED ====="
        )

        print(
            "REASON:",
            "no semantic requirements or technical hints to verify"
        )

        return (
            True,
            resolved_fields
        )

    print(
        "\n===== DYNAMIC MODEL COMPATIBILITY PASSED ====="
    )

    print(
        "REQUIRED SEMANTIC CONCEPTS:",
        semantic_concepts
    )

    print(
        "REQUIRED FIELD HINTS:",
        required_fields
    )

    print(
        "RESOLVED FIELDS:",
        resolved_fields
    )

    return (
        True,
        resolved_fields
    )


# ==========================================================
# FIND COMPATIBLE MODEL
# ==========================================================

async def _dynamic_find_compatible_model(
    odoo_client,
    metadata_service,
    current_model: str,
    current_metadata: Dict[str, Any],
    current_fields: Dict[str, Dict[str, Any]],
    params: Dict[str, Any],
    user_message: str,
    semantic_concepts: Optional[
        List[Dict[str, Any]]
    ] = None,
    dynamic_model_candidates: Optional[
        List[Dict[str, Any]]
    ] = None,
) -> Optional[
    Tuple[
        str,
        Dict[str, Dict[str, Any]],
        Dict[str, Any],
        Dict[str, str],
    ]
]:

    if semantic_concepts is None:

        semantic_concepts = []

    semantic_concepts = (
        _dynamic_normalize_semantic_concepts(
            semantic_concepts
        )
    )

    if dynamic_model_candidates is None:

        dynamic_model_candidates = []

    if not isinstance(
        dynamic_model_candidates,
        list
    ):

        dynamic_model_candidates = []

    required_fields = (
        _dynamic_parameter_root_fields(
            params
        )
    )

    if semantic_concepts:

        required_fields = [

            field

            for field in required_fields

            if _dynamic_non_generic_tokens(
                _normalize_semantic_tokens(
                    field
                ),
                fields=current_fields,
            )

        ]

    if (
        not required_fields
        and not semantic_concepts
    ):

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
        "REQUIRED FIELD HINTS:",
        required_fields
    )

    print(
        "REQUIRED SEMANTIC CONCEPTS:",
        semantic_concepts
    )

    # ======================================================
    # CANDIDATI PRIORITARI PROVENIENTI DAL DISCOVERY
    # ======================================================

    preferred_candidates = []

    seen_models = set()

    for candidate in dynamic_model_candidates:

        if not isinstance(
            candidate,
            dict
        ):

            continue

        candidate_model = str(
            candidate.get(
                "model",
                ""
            )
            or ""
        ).strip()

        if not candidate_model:

            continue

        if candidate_model == current_model:

            continue

        model_key = candidate_model.lower()

        if model_key in seen_models:

            continue

        seen_models.add(
            model_key
        )

        preferred_candidates.append(
            (
                float(
                    candidate.get(
                        "_score",
                        0.0
                    )
                    or 0.0
                ),
                candidate_model,
                candidate,
            )
        )

    # ======================================================
    # DISCOVERY GLOBALE DEI MODELLI REALI
    # ======================================================

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

    preferred_models = set()

    # ======================================================
    # DISCOVERY CANDIDATES COME PRIMA
    # ======================================================

    for (
        discovery_score,
        candidate_model,
        candidate_record,
    ) in preferred_candidates:

        if not candidate_model:

            continue

        preferred_models.add(
            candidate_model
        )

        discovery_prior = min(
            max(
                discovery_score,
                0.0
            ) * 4.0,
            80.0
        )

        model_candidates.append(
            (
                80.0 + discovery_prior,

                candidate_model,

                {
                    "model":
                        candidate_model,

                    "name":
                        candidate_record.get(
                            "name",
                            ""
                        ),

                    "state":
                        candidate_record.get(
                            "state",
                            ""
                        ),

                },
            )
        )

    # ======================================================
    # ALTRI MODELLI REALI
    # ======================================================

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

        if candidate_model in preferred_models:

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
    # BOUNDING
    # ======================================================

    MAX_DYNAMIC_MODEL_CANDIDATES = 50

    if len(
        model_candidates
    ) > MAX_DYNAMIC_MODEL_CANDIDATES:

        preferred_model_names = {
            candidate_model

            for (
                _score,
                candidate_model,
                _record
            ) in model_candidates

            if candidate_model in preferred_models
        }

        bounded_candidates = []

        for candidate in model_candidates:

            if candidate[1] in preferred_model_names:

                bounded_candidates.append(
                    candidate
                )

        for candidate in model_candidates:

            if len(
                bounded_candidates
            ) >= MAX_DYNAMIC_MODEL_CANDIDATES:

                break

            if candidate[1] in preferred_model_names:

                continue

            bounded_candidates.append(
                candidate
            )

        model_candidates = (
            bounded_candidates
        )

        model_candidates.sort(
            key=lambda item: (
                -item[0],
                item[1].lower(),
            )
        )

    print(
        "\n===== DYNAMIC MODEL CANDIDATE VERIFICATION ====="
    )

    print(
        "TOTAL MODEL CANDIDATES:",
        len(
            model_candidates
        )
    )

    print(
        "VERIFYING BOUNDED TOP CANDIDATES AGAINST ir.model.fields"
    )

    print(
        "\n===== DYNAMIC MODEL CANDIDATES ====="
    )

    for (
        score,
        candidate_model,
        record
    ) in model_candidates[:30]:

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

        for (
            _score,
            candidate_model,
            _record
        ) in model_candidates

    ]

    if not candidate_model_names:

        return None

    # ======================================================
    # METADATA REALI DEI CAMPI
    # ======================================================

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

    # ======================================================
    # MODEL VERIFICATION
    # ======================================================

    for (
        model_score,
        candidate_model,
        model_record
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
            len(
                candidate_fields
            )
        )

        compatibility = (
            _dynamic_required_fields_compatible(
                params=params,
                fields=candidate_fields,
                user_message=user_message,
                semantic_concepts=semantic_concepts,
                model=candidate_model,
                metadata=model_record,
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

        semantic_quality_score = (
            _dynamic_model_resolution_score(
                params=params,
                fields=candidate_fields,
                semantic_concepts=semantic_concepts,
                resolved_fields=resolved_fields,
            )
        )

        exact_bonus = 0.0

        for (
            source_field,
            resolved_field
        ) in resolved_fields.items():

            if (
                source_field
                == resolved_field
            ):

                exact_bonus += 15.0

        final_score = (
            model_score
            + semantic_quality_score
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
            "SEMANTIC QUALITY SCORE:",
            semantic_quality_score
        )

        print(
            "EXACT FIELD BONUS:",
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

    # ======================================================
    # FULL DISCOVERY DAL METADATA SERVICE
    # ======================================================

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
        len(
            discovered_fields
        )
    )

    final_compatibility = (
        _dynamic_required_fields_compatible(
            params=params,
            fields=discovered_fields,
            user_message=user_message,
            semantic_concepts=semantic_concepts,
            model=selected_model,
            metadata=discovered_metadata,
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
        final_resolved_fields,
    )


def _ensure_read_group_fields_include_groupby(
    params: Dict[str, Any]
) -> Dict[str, Any]:

    if not isinstance(
        params,
        dict
    ):
        return params

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

    if not isinstance(
        fields,
        list
    ):

        fields = []

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

    if not isinstance(
        groupby,
        list
    ):

        groupby = []

    normalized_fields = list(
        fields
    )

    field_bases = set()

    for field_expression in normalized_fields:

        base = _dynamic_expression_base(
            field_expression
        )

        if base:

            field_bases.add(
                base
            )

    for group_expression in groupby:

        group_expression = (
            group_expression.strip()
        )

        if not group_expression:
            continue

        if group_expression == "__count":
            continue

        if group_expression not in normalized_fields:

            normalized_fields.append(
                group_expression
            )

            print(
                "\n===== READ_GROUP STRUCTURAL NORMALIZATION ====="
            )

            print(
                "GROUPBY EXPRESSION ADDED TO FIELDS:",
                group_expression
            )

            print(
                "\n===== READ_GROUP STRUCTURAL NORMALIZATION ====="
            )

            print(
                "GROUPBY FIELD ADDED TO FIELDS:",
                base
            )

    params["fields"] = (
        normalized_fields
    )

    params["groupby"] = (
        groupby
    )

    return params


# ==========================================================
# SEMANTIC CONTEXT EXTRACTION
# ==========================================================

def _collect_semantic_concepts_from_state(
    state: Any,
    dynamic_model_candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:

    """
    Recupera esclusivamente il contesto semantico prodotto
    dalla pipeline a monte.

    Priorità:

    1. state.semantic_concepts
    2. _request_semantic_concepts dei candidati
    3. _semantic_concepts dei candidati

    Nessun concetto viene inventato localmente.
    """

    collected = []
    seen = set()

    def add_entries(
        entries: Any
    ):

        if not isinstance(
            entries,
            list
        ):

            return

        for entry in entries:

            if isinstance(
                entry,
                str
            ):

                concept = entry.strip()

                aliases = []

            elif isinstance(
                entry,
                dict
            ):

                concept = entry.get(
                    "concept"
                )

                aliases = entry.get(
                    "queries",
                    []
                )

                if not isinstance(
                    aliases,
                    list
                ):

                    aliases = []

            else:

                continue

            if not isinstance(
                concept,
                str
            ):

                continue

            concept = concept.strip()

            if not concept:

                continue

            concept_key = " ".join(
                _normalize_semantic_tokens(
                    concept
                )
            )

            if not concept_key:

                continue

            if concept_key in seen:

                continue

            normalized_aliases = []

            alias_seen = set()

            for alias in aliases:

                if not isinstance(
                    alias,
                    str
                ):

                    continue

                alias = alias.strip()

                if not alias:

                    continue

                alias_key = " ".join(
                    _normalize_semantic_tokens(
                        alias
                    )
                )

                if (
                    not alias_key
                    or alias_key in alias_seen
                ):

                    continue

                alias_seen.add(
                    alias_key
                )

                normalized_aliases.append(
                    alias
                )

            if not normalized_aliases:

                normalized_aliases = [
                    concept
                ]

            collected.append(
                {
                    "concept":
                        concept,

                    "queries":
                        normalized_aliases[:8],
                }
            )

            seen.add(
                concept_key
            )

    # ------------------------------------------------------
    # 1. State
    # ------------------------------------------------------

    if isinstance(
        state,
        dict
    ):

        add_entries(
            state.get(
                "semantic_concepts"
            )
        )

        for key in (
            "semantic_scope",
            "scope_result",
            "request_scope",
            "semantic_validation",
        ):

            value = state.get(
                key
            )

            if isinstance(
                value,
                dict
            ):

                add_entries(
                    value.get(
                        "concepts"
                    )
                )

            elif isinstance(
                value,
                list
            ):

                add_entries(
                    value
                )

    # ------------------------------------------------------
    # 2. Request-level context
    # ------------------------------------------------------

    for candidate in dynamic_model_candidates:

        if not isinstance(
            candidate,
            dict
        ):

            continue

        add_entries(
            candidate.get(
                "_request_semantic_concepts"
            )
        )

    # ------------------------------------------------------
    # 3. Candidate-local context
    # ------------------------------------------------------

    for candidate in dynamic_model_candidates:

        if not isinstance(
            candidate,
            dict
        ):

            continue

        add_entries(
            candidate.get(
                "_semantic_concepts"
            )
        )

    return collected[:8]


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
    # DYNAMIC MODEL DISCOVERY CONTEXT
    # ======================================================

    dynamic_model_candidates = (
        state.get(
            "dynamic_model_candidates",
            []
        )
    )

    if not isinstance(
        dynamic_model_candidates,
        list
    ):

        dynamic_model_candidates = []

    semantic_concepts = (
        _collect_semantic_concepts_from_state(
            state=state,
            dynamic_model_candidates=dynamic_model_candidates,
        )
    )

    print(
        "\n===== ODOO AGENT SEMANTIC CONTEXT ====="
    )

    print(
        "DYNAMIC MODEL CANDIDATES:",
        len(
            dynamic_model_candidates
        )
    )

    print(
        "SEMANTIC CONCEPTS:",
        semantic_concepts
    )

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

        print(
            "\n===== MODEL MISSING FROM PLANNER ====="
        )

        print(
            "ATTEMPTING DYNAMIC MODEL DISCOVERY"
        )

        if method not in {
            "search",
            "search_read",
            "search_count",
            "read_group",
        }:

            raise ValueError(
                "Il piano Portant non contiene il modello "
                "e il metodo richiesto non è supportato "
                "dal dynamic discovery."
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
    # DOMAIN DEFAULT
    # ======================================================

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

    discovered_metadata: Dict[str, Any] = {}

    discovered_fields: Dict[
        str,
        Dict[str, Any]
    ] = {}

    discovered_tree_view: Optional[
        Dict[str, Any]
    ] = None

    resolved_fields: Dict[
        str,
        str
    ] = {}

    if model:

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

    else:

        print(
            "\n===== MODEL DISCOVERY DEFERRED ====="
        )

        print(
            "REASON:",
            "planner did not provide a model"
        )

    # ======================================================
    # MODEL FALLBACK / METADATA DISCOVERY
    # ======================================================

    if discovered_schema is None:

        if not model:

            fallback_result = await (
                _dynamic_find_compatible_model(
                    odoo_client=odoo_client,

                    metadata_service=metadata_service,

                    current_model="",

                    current_metadata={},

                    current_fields={},

                    params=params,

                    user_message=current_user_message,

                    semantic_concepts=semantic_concepts,

                    dynamic_model_candidates=(
                        dynamic_model_candidates
                    ),
                )
            )

            if fallback_result is None:

                raise ValueError(
                    "Il planner non ha fornito un modello "
                    "e il dynamic model discovery non ha trovato "
                    "alcun modello Odoo compatibile."
                )

            (
                model,
                discovered_fields,
                discovered_metadata,
                fallback_resolved_fields,
            ) = fallback_result

            resolved_fields = (
                fallback_resolved_fields
                or {}
            )

            params = (
                _dynamic_apply_resolved_field_mappings(
                    params=params,
                    resolved_fields=resolved_fields,
                )
            )

            odoo_validator.register_dynamic_model(
                model=model,

                metadata=discovered_metadata,

                fields=discovered_fields,
            )

            odoo_validator.register_dynamic_fields(
                model=model,

                fields=discovered_fields,
            )

            try:

                discovered_tree_view = await (
                    metadata_service.discover_tree_view(
                        model_name=model,
                        use_cache=True,
                    )
                )

            except Exception as exc:

                print(
                    "\n===== DYNAMIC FALLBACK TREE VIEW ERROR ====="
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

                discovered_tree_view = None

            discovered_schema = {
                "metadata":
                    discovered_metadata,

                "fields":
                    discovered_fields,

                "tree_view":
                    discovered_tree_view,
            }

            is_static_model = (
                model in ODOO_MODELS
            )

            print(
                "\n===== DYNAMIC MODEL FALLBACK APPLIED ====="
            )

            print(
                "FALLBACK MODEL:",
                model
            )

        elif not is_static_model:

            print(
                "DYNAMIC DISCOVERY: MODEL NOT FOUND"
            )

            raise ValueError(
                "Il modello Portant richiesto non esiste "
                f"nell'istanza Odoo: {model}"
            )

        else:

            print(
                "\n===== REAL MODEL METADATA UNAVAILABLE ====="
            )

            print(
                "MODEL:",
                model
            )

            raise ValueError(
                "I metadata reali Odoo del modello "
                f"'{model}' non sono disponibili."
            )

    # ======================================================
    # MODEL METADATA DISPONIBILI
    # ======================================================

    if not isinstance(
        discovered_schema,
        dict
    ):

        raise ValueError(
            f"Metadata Odoo non validi per il modello '{model}'."
        )

    discovered_metadata = (
        discovered_schema.get(
            "metadata",
            discovered_metadata
        )
    )

    discovered_fields = (
        discovered_schema.get(
            "fields",
            discovered_fields
        )
    )

    discovered_tree_view = (
        discovered_schema.get(
            "tree_view"
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

    if not isinstance(
            discovered_tree_view,
            dict
        ):

        discovered_tree_view = None

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

    # ======================================================
    # DEBUG RELAZIONI
    # ======================================================

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
        relation_label
    ) in relation_fields:

        print(
            " -",
            relation_field_name,
            "|",
            relation_label,
            "| relation:",
            relation_model
        )

    # ======================================================
    # REGISTRAZIONE MODELLO DINAMICO
    # ======================================================

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

    # ======================================================
    # MODEL COMPATIBILITY CHECK
    # ======================================================

    model_compatibility = (
        _dynamic_required_fields_compatible(
            params=params,
            fields=discovered_fields,
            user_message=current_user_message,
            semantic_concepts=semantic_concepts,
            model=model,
            metadata=discovered_metadata,
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
            "required query fields/concepts are not compatible"
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

                semantic_concepts=semantic_concepts,

                dynamic_model_candidates=(
                    dynamic_model_candidates
                ),
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
            fallback_resolved_fields,
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

        model = fallback_model

        discovered_fields = (
            fallback_fields
        )

        discovered_metadata = (
            fallback_metadata
        )

        resolved_fields = (
            fallback_resolved_fields
            or {}
        )

        params = _dynamic_apply_resolved_field_mappings(
            params=params,

            resolved_fields=resolved_fields,
        )

        parameters["model"] = model

        is_static_model = (
            model in ODOO_MODELS
        )

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

        try:

            discovered_tree_view = await (
                metadata_service.discover_tree_view(
                    model_name=model,
                    use_cache=True,
                )
            )

        except Exception as exc:

            print(
                "\n===== MODEL FALLBACK TREE VIEW ERROR ====="
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

            discovered_tree_view = None

        discovered_schema = {

            "metadata":
                discovered_metadata,

            "fields":
                discovered_fields,

            "tree_view":
                discovered_tree_view,

        }

    # ======================================================
    # DYNAMIC FIELD / GROUPBY / ORDERBY RESOLUTION
    # ======================================================

    params = _dynamic_apply_field_resolution(
        params=params,

        fields=discovered_fields,

        user_message=current_user_message,

        semantic_concepts=semantic_concepts,

        tree_view=discovered_tree_view,

        prefer_tree_view=(
            method == "search_read"
        ),
    )

    params = _dynamic_remove_invalid_fields(
        params=params,

        fields=discovered_fields,

        user_message=current_user_message,
    )

    if method == "read_group":

        params = (
            _ensure_read_group_fields_include_groupby(
                params
            )
        )

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

    params = _dynamic_repair_domain(
        params=params,

        fields=discovered_fields,

        user_message=current_user_message,
    )

    if resolved_fields:

        params = (
            _dynamic_apply_resolved_field_mappings(
                params=params,

                resolved_fields=resolved_fields,
            )
        )

    if method == "read_group":

        params = (
            _ensure_read_group_fields_include_groupby(
                params
            )
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

    if method == "read_group":

        params = (
            _ensure_read_group_fields_include_groupby(
                params
            )
        )

        parameters["params"] = (
            params
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

        final_params = (
            _ensure_read_group_fields_include_groupby(
                final_params
            )
        )

    validated["params"] = (
        final_params
    )

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

    normalized = _normalize_odoo_result(
        result=result,

        method=method,

        params=final_params,
    )

    normalized = _attach_record_links(
        normalized=normalized,

        model=model,

        base_url=odoo_client.base_url,
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