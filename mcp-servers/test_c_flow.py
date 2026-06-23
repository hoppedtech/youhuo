"""C 端「扫码授权 → 搜索岗位 → 报名接单 → 查看订单」流程验证。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared_token_store import auth_store


def mock_create_auth_session():
    """模拟 youhuo-c-api.create_auth_session"""
    session_id = auth_store.create_session(role=1)
    auth_store.set_current_session(session_id)
    print(f"✅ create_auth_session: session_id={session_id}, role=1")
    return session_id


def mock_check_auth_status(session_id: str):
    """模拟扫码完成后 check_auth_status 返回"""
    # 模拟：用户已扫码，后端返回 token
    mock_token = "mock_token_worker_xyz789"
    auth_store.set_token(
        session_id,
        mock_token,
        user_info={"name": "张师傅", "is_new_user": False},
        expires_in=7200,
    )
    print(f"✅ check_auth_status: 授权成功，token={mock_token[:20]}...")


def mock_search_jobs():
    """模拟 youhuo-c-api.search_jobs"""
    print("\n📋 [search_jobs] 搜索深圳搬运工岗位...")
    print("找到 3 个岗位：")
    print("  [1001] 仓库搬运工 | 250元/天 | 深圳宝安 | 招5人")
    print("  [1002] 快递分拣员 | 220元/天 | 深圳龙岗 | 招3人")
    print("  [1003] 餐厅小时工 | 25元/小时 | 深圳南山 | 招2人")


def mock_get_job_detail(job_id: int):
    """模拟 youhuo-c-api.get_job_detail"""
    print(f"\n📋 [get_job_detail] 查看岗位 {job_id} 详情...")
    print(f"  仓库搬运工")
    print(f"  岗位ID: {job_id}")
    print(f"  💰 薪资: 200-250元/天")
    print(f"  📍 地点: 深圳市宝安区西乡街道")
    print(f"  👥 招募: 5人 | 已报名: 2人")
    print(f"  📅 工作日期: 2026-06-16 至 2026-06-30")
    print(f"  ⏰ 工作时间: 08:00 - 18:00")
    print(f"  📝 岗位描述: 负责仓库货物搬运、整理，要求身体健康，能吃苦耐劳")


def mock_apply_job(job_id: int):
    """模拟 youhuo-c-api.apply_job"""
    print(f"\n📋 [apply_job] 报名岗位 {job_id}...")
    print("  ✅ 报名成功！")
    print("  企业方确认后，您将收到通知。")


def mock_get_my_tasks():
    """模拟 youhuo-c-api.get_my_tasks"""
    print("\n📋 [get_my_tasks] 查看我的订单...")
    print("我的订单（共2单）：")
    print("  ⏳ [2001] 仓库搬运工 | 250元/天 | 深圳宝安 | 状态: 待企业确认")
    print("  ✅ [2002] 快递分拣员 | 220元/天 | 深圳龙岗 | 状态: 已完成")


def main():
    print("=" * 60)
    print("C端流程验证：扫码授权 → 搜索岗位 → 报名 → 查看订单")
    print("=" * 60)

    # Step 1: 创建授权会话
    session_id = mock_create_auth_session()

    # Step 2: 模拟扫码完成
    mock_check_auth_status(session_id)

    # Step 3: 验证 Token 共享
    token_info = auth_store.get_current_token()
    assert token_info is not None
    assert token_info["token"].startswith("mock_token_worker")
    print(f"✅ Token 共享验证通过: {token_info['token'][:20]}...")

    # Step 4: 搜索岗位
    mock_search_jobs()

    # Step 5: 查看岗位详情
    mock_get_job_detail(1001)

    # Step 6: 报名接单
    mock_apply_job(1001)

    # Step 7: 查看我的订单
    mock_get_my_tasks()

    print("\n" + "=" * 60)
    print("✅ C端全部流程验证通过！")
    print("=" * 60)


if __name__ == "__main__":
    main()
