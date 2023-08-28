import math
import random
import string
from typing import Dict, List, Optional

# UID-User mapping
UID_USERS = {
    # UID: User Email
    "1000": "dev@markhh.com",
}

# User report_key mapping
USER_REPORTKEYS = {
    # user_id: {}
    "1000": {
        # report_key: desc
        "dev@markhh.com": "default",
    },
}


ALL_REPORTKEYS = set(["dev@markhh.com"])


def check_user_id(user_id: str) -> bool:
    """
    Check if the user_id is valid
    """
    if not isinstance(user_id, str):
        return False
    if user_id not in UID_USERS:
        return False

    if user_id not in USER_REPORTKEYS:
        USER_REPORTKEYS[user_id] = {}

    return True


###############################################################################
### Reporting Passcode


def generate_random_report_key(length: int = 8) -> str:
    """
    Generate a random report_key of the given length
    """
    while True:
        code = "".join(
            random.choices(string.ascii_letters + string.digits, k=length)
        ).upper()
        if code not in ALL_REPORTKEYS:
            return code


def create_new_report_key(
    user_id: str,
    report_key: Optional[str] = "",
    report_key_desc: Optional[str] = "",
):
    # check user_id is valid
    valid_uid = check_user_id(user_id)
    if not valid_uid:
        raise ValueError(f"Invalid user_id: {user_id}")
    # generate a new report_key if not provided
    if not report_key:
        report_key = generate_random_report_key()
    # check report_key is valid and not in use
    ...  # TODO
    # check report_key is valid
    ...  # TODO
    # add to report_key list
    ALL_REPORTKEYS.add(report_key)
    # add to user report_key_desc list
    USER_REPORTKEYS[user_id][report_key] = report_key_desc
    return report_key


def delete_passcode(user_id: str, passcode: str) -> None:
    # check user_id is valid
    valid_uid = check_user_id(user_id)
    if not valid_uid:
        raise ValueError(f"Invalid user_id: {user_id}")
    # check passcode exists
    if passcode not in USER_REPORTKEYS[user_id]:
        raise ValueError("Passcode does not exist")  # TODO: maybe refine this
    # remove from user passcode list
    del USER_REPORTKEYS[user_id][passcode]
    # remove from passcode list
    if passcode in ALL_REPORTKEYS:
        ALL_REPORTKEYS.remove(passcode)
    else:
        print(
            "Unexpected Error: passcode exists in user list but not in all list, code logic might be wrong"
        )
    return


###############################################################################
### Team Code

USER_TEAM_INFO = {
    # user_id: {}
    "xxxxxxx": {
        # code: desc
        "default": {
            "team_code": "default",
            "team_name": "My Team",
            "team_desc": "My Team Description",
        },
    },
}

TEAM_CODE_MACHINE_MAPPING: Dict[str, List[str]] = {}


def generate_random_team_code(length: int = 8) -> str:
    """
    Generate a random team code of the given length
    """
    while True:
        code = "".join(
            random.choices(string.ascii_letters + string.digits, k=length)
        ).upper()
        if code not in TEAM_CODE_MACHINE_MAPPING:
            return code


def create_new_team(
    user_id: str,
    team_code: Optional[str] = "",
    team_name: Optional[str] = "",
    team_desc: Optional[str] = "",
):
    # check user_id is valid
    valid_uid = check_user_id(user_id)
    if not valid_uid:
        raise ValueError(f"Invalid user_id: {user_id}")
    # generate a new team code if not provided
    if not team_code:
        team_code = generate_random_team_code()
    # check team code is valid and not in use
    ...  # TODO
    # check team_name is valid
    ...  # TODO
    # check team_desc is valid
    ...  # TODO
    # add to TEAM_CODE_MACHINE_MAPPING
    TEAM_CODE_MACHINE_MAPPING[team_code] = []
    # add to USER_TEAM_INFO
    USER_TEAM_INFO[user_id][team_code] = {
        "team_code": team_code,
        "team_name": team_name,
        "team_desc": team_desc,
    }
    return team_code


def delete_team(user_id: str, team_code: str) -> None:
    # check user_id is valid
    valid_uid = check_user_id(user_id)
    if not valid_uid:
        raise ValueError(f"Invalid user_id: {user_id}")  # TODO: maybe refine this
    # check team_code exists
    if team_code not in USER_TEAM_INFO[user_id]:
        raise ValueError("Team does not exist")  # TODO: maybe refine this
    # remove from USER_TEAM_INFO
    del USER_TEAM_INFO[user_id][team_code]
    # remove from TEAM_CODE_MACHINE_MAPPING
    if team_code in TEAM_CODE_MACHINE_MAPPING:
        del TEAM_CODE_MACHINE_MAPPING[team_code]
    else:
        print(
            "Unexpected Error: team_code exists in USER_TEAM_INFO but not in TEAM_CODE_MACHINE_MAPPING, code logic might be wrong"
        )
    return


def valid_machine_uuid(machine_uuid: str) -> bool:
    ...
    return True


def add_machines_to_team(
    user_id: str, team_code: str, machine_uuids: List[str]
) -> List[Dict[str, str]]:
    # check user_id is valid
    valid_uid = check_user_id(user_id)
    if not valid_uid:
        raise ValueError(f"Invalid user_id: {user_id}")
    # check team_code exists
    if team_code not in USER_TEAM_INFO[user_id]:
        raise ValueError("Team does not exist")
    if team_code not in TEAM_CODE_MACHINE_MAPPING:
        TEAM_CODE_MACHINE_MAPPING[team_code] = []
        print(
            "Unexpected Error: team_code exists in USER_TEAM_INFO but not in TEAM_CODE_MACHINE_MAPPING, code logic might be wrong"
        )
    # check machine_uuids are valid
    results = []
    for uuid in machine_uuids:
        if not valid_machine_uuid(uuid):
            results.append(
                {
                    "uuid": uuid,
                    "status": "failed",
                    "description": "Invalid machine uuid",
                }
            )
            continue
        if uuid in TEAM_CODE_MACHINE_MAPPING[team_code]:
            results.append(
                {
                    "uuid": uuid,
                    "status": "ok",
                    "description": "Machine already in team",
                }
            )
            continue
        # TODO: check if the user has access to that machine
        ...

        TEAM_CODE_MACHINE_MAPPING[team_code].append(uuid)
        results.append(
            {
                "uuid": uuid,
                "status": "ok",
                "description": "Machine added to team",
            }
        )
    return results


def remove_machines_from_team(user_id: str, team_code: str, machine_uuids: List[str]):
    ...


if __name__ == "__main__":
    print(generate_random_report_key())
