import os
import random
import string
import sys
from datetime import datetime
from typing import Dict, List, Optional, Set, Union

from rich import print
from supabase import Client

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import server.database as db
from server.auth import init_supabase, sign_myself_in, sign_out
from server.data_model import MachineStatus, ReportKey, ViewGroup

supabase = init_supabase()


if __name__ == "__main__":
    session = sign_myself_in(supabase)
    user_id = session.user.id
    try:
        report_keys = db.get_user_report_keys_supabase(supabase=supabase)
        print(report_keys)
        # create_new_report_key_supabase(
        #     supabase=supabase,
        #     user_id=user_id,
        #     report_key_desc="My second key creation test",
        # )
        # report_keys = get_user_report_keys_supabase(supabase=supabase)
        # print(f"After: {report_keys}")

        print("=" * 80)
        view_groups = db.get_user_view_groups_supabase(
            supabase=supabase, user_id=user_id
        )
        print(view_groups)
        # view_group = create_new_view_group_supabase(
        #     supabase=supabase,
        #     user_id=user_id,
        #     view_group=ViewGroup(
        #         view_name="My testing view group",
        #         view_desc="My testing view group description",
        #         view_enabled=True,
        #         # view_machines=["testing"],
        #     ),
        # )
        # print(f"returned view_group: {view_group}")

        print("=" * 80)
        # check a specific view group
        view_group = db.check_view_group_supabase(supabase, view_key="BJHNNM")
        print(f"before update view_group:")
        print(view_group)
        # test add machine to view
        view_group = db.update_machines_in_view_supabase(
            supabase=supabase,
            user_id=user_id,
            view_key="BJHNNM",
            overwrite=["machine1", "machine2"],
        )
        print(f"returned view_group:")
        print(view_group)

    except Exception as e:
        raise e
    finally:
        sign_out(supabase)
        print("Signed out")
