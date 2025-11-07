import time
from typing import Any, Dict, List
from motor.motor_asyncio import AsyncIOMotorDatabase


async def aggregate_form_statistics(db: AsyncIOMotorDatabase, form_id: str) -> Dict[str, Any]:
    """Aggregate statistics for a specific form"""
    # Count total sessions
    total_sessions = await db.sessions.count_documents({"formId": form_id})
    
    # Count completed sessions (sessions with all required fields)
    form = await db.forms.find_one({"id": form_id}, {"_id": 0})
    if not form:
        return {}
    
    required_fields = [f["id"] for f in form.get("fields", []) if f.get("required", False)]
    completed_sessions = 0
    total_answers = 0
    field_answer_counts = {}
    
    async for session in db.sessions.find({"formId": form_id}):
        answers = session.get("answers", {})
        total_answers += len(answers)
        
        # Count answers per field
        for field_id, value in answers.items():
            field_answer_counts[field_id] = field_answer_counts.get(field_id, 0) + 1
        
        # Check if completed
        if required_fields:
            if all(field_id in answers for field_id in required_fields):
                completed_sessions += 1
        elif len(answers) > 0:
            completed_sessions += 1
    
    # Calculate completion rate
    completion_rate = (completed_sessions / total_sessions * 100) if total_sessions > 0 else 0
    
    # Get field popularity
    field_popularity = []
    for field in form.get("fields", []):
        field_id = field.get("id")
        answer_count = field_answer_counts.get(field_id, 0)
        field_popularity.append({
            "field_id": field_id,
            "label": field.get("label", field_id),
            "answer_count": answer_count,
            "popularity_score": (answer_count / total_sessions * 100) if total_sessions > 0 else 0
        })
    field_popularity.sort(key=lambda x: x["answer_count"], reverse=True)
    
    return {
        "form_id": form_id,
        "form_title": form.get("title", form_id),
        "statistics": {
            "total_sessions": total_sessions,
            "completed_sessions": completed_sessions,
            "completion_rate": round(completion_rate, 2),
            "total_answers": total_answers,
            "avg_answers_per_session": round(total_answers / total_sessions, 2) if total_sessions > 0 else 0
        },
        "field_popularity": field_popularity[:10],  # Top 10
        "last_updated": int(time.time())
    }


async def aggregate_all_forms_statistics(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """Aggregate statistics for all forms"""
    total_forms = await db.forms.count_documents({})
    total_sessions = await db.sessions.count_documents({})
    
    # Get all forms
    forms = []
    async for form in db.forms.find({}, {"_id": 0}):
        forms.append(form)
    
    # Aggregate per form
    form_stats = []
    for form in forms:
        form_id = form.get("id")
        stats = await aggregate_form_statistics(db, form_id)
        if stats:
            form_stats.append(stats)
    
    # Calculate overall metrics
    total_completed = sum(s["statistics"]["completed_sessions"] for s in form_stats)
    overall_completion_rate = (total_completed / total_sessions * 100) if total_sessions > 0 else 0
    
    # Most popular forms
    form_stats_sorted = sorted(
        form_stats,
        key=lambda x: x["statistics"]["total_sessions"],
        reverse=True
    )
    
    # Most popular fields across all forms
    all_field_counts = {}
    for stats in form_stats:
        for field in stats.get("field_popularity", []):
            field_label = field["label"]
            all_field_counts[field_label] = all_field_counts.get(field_label, 0) + field["answer_count"]
    
    top_fields = sorted(
        [{"label": k, "count": v} for k, v in all_field_counts.items()],
        key=lambda x: x["count"],
        reverse=True
    )[:10]
    
    return {
        "overall": {
            "total_forms": total_forms,
            "total_sessions": total_sessions,
            "total_completed_sessions": total_completed,
            "overall_completion_rate": round(overall_completion_rate, 2),
            "avg_sessions_per_form": round(total_sessions / total_forms, 2) if total_forms > 0 else 0
        },
        "top_forms": form_stats_sorted[:10],
        "top_fields": top_fields,
        "forms": form_stats,
        "last_updated": int(time.time())
    }


async def get_timeseries_data(db: AsyncIOMotorDatabase, days: int = 7) -> Dict[str, Any]:
    """Get time series data for sessions and completions"""
    from datetime import datetime, timedelta
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Get all sessions and group by date manually
    # Since sessions might not have createdAt, we'll use _id ObjectId timestamp
    daily_sessions_map = {}
    
    async for session in db.sessions.find({}):
        # Try to get timestamp from _id ObjectId
        session_id = session.get("_id")
        if session_id:
            try:
                # ObjectId contains timestamp
                timestamp = session_id.generation_time.timestamp()
                if start_date.timestamp() <= timestamp <= end_date.timestamp():
                    date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
                    daily_sessions_map[date_str] = daily_sessions_map.get(date_str, 0) + 1
            except Exception:
                pass
    
    # Convert to list
    daily_sessions = [
        {"date": date, "sessions": count}
        for date, count in sorted(daily_sessions_map.items())
    ]
    
    return {
        "period": f"{days} days",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily_sessions": daily_sessions
    }


async def upsert_gold_data(db: AsyncIOMotorDatabase, form_id: str = None):
    """Upsert gold layer data for a form or all forms"""
    if form_id:
        stats = await aggregate_form_statistics(db, form_id)
        if stats:
            await db.gold.update_one(
                {"form_id": form_id},
                {"$set": stats},
                upsert=True
            )
    else:
        # Aggregate all
        all_stats = await aggregate_all_forms_statistics(db)
        await db.gold.update_one(
            {"type": "overall"},
            {"$set": all_stats},
            upsert=True
        )

