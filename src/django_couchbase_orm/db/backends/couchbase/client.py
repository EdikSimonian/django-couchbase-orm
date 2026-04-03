"""Couchbase database client for manage.py dbshell."""

from django.db.backends.base.client import BaseDatabaseClient


class DatabaseClient(BaseDatabaseClient):
    executable_name = "cbq"

    @classmethod
    def settings_to_cmd_args_env(cls, settings_dict, parameters):
        args = [cls.executable_name]
        host = settings_dict.get("HOST", "couchbase://localhost")
        # Strip scheme for cbq tool.
        host = host.replace("couchbase://", "").replace("couchbases://", "")
        args.extend(["-e", f"http://{host}:8093"])

        user = settings_dict.get("USER")
        if user:
            args.extend(["-u", user])

        password = settings_dict.get("PASSWORD")
        env = None
        if password:
            env = {"CB_PASSWORD": password}

        args.extend(parameters)
        return args, env
