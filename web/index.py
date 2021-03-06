# -*- coding: utf-8 -*-
"""
    Storamen web app
    ~~~~~~~~~~~~~~~~
    powered by bottle.py

    :copyright: 20150720 by raptor.zh@gmail.com.
"""
import os
import shutil
import logging

from bottle import Bottle, static_file, view
from bottle.ext.sqlalchemy import Plugin as SAPlugin

from config import config_name, reload_config
from db import web, scan
from db.common import get_fullname, save_config, format_size
from db.model import engine, metadata
from web.bottle_plugins.auth import AuthPlugin
from web.bottle_plugins.params import ParamsPlugin

logger = logging.getLogger(__name__)
config = reload_config()

app = Bottle()
app.install(SAPlugin(engine, metadata, keyword='db'))
app.install(ParamsPlugin())
app.install(AuthPlugin(dbkeyword='db'))


@app.get("/")
@view("index")
def get_():
    return {"static_path": config['static_path'], "web_path": config['web_path']}


@app.get("/static/<filename:path>")
def get_static(filename):
    return static_file(filename, root=get_fullname("static"))


@app.get("/status")
def get_status(db):
    info = web.get_status(db)
    if info:
        info['work_dir'] = config['work_dir']
        info['size'] = format_size(info['size'])
        info['updated'] = info['updated'][:-7] if info['updated'] else None
    return info


@app.post("/scan")
def post_scan(db):
    msg = scan.reset_scanner()
    if msg is None:
        msg = scan.spawn_scanner(config['work_dir'])
    return {"message": msg}


@app.get("/scan/progress")
def get_scan_progress(db):
    msg = scan.reset_scanner()
    if msg is None:
        scan.set_progress(100, "", 0)
    return web.get_progress()


@app.get("/search")
def get_search(db, tags, page='0'):
    tags = [t.strip() for t in tags.replace(" ", ",").split(",") if t.strip() != ""]
    res = web.get_search(db, tags[:8], int(page))
    return {"searchfiles": res}


@app.get("/duplicated")
def get_duplicated(db, since_size='0'):
    if not since_size:
        since_size = 0
    res = web.get_duplist(db, int(since_size))
    return {"dupfiles": res}


def remove_file_or_dir(db, id):
    name = web.remove_dup(db, id, os.path.expanduser(config["work_dir"]))
    if not name:
        logger.warning("Invalid id: {}".format(id))
        return "invalid_id"
    name = os.path.join(os.path.expanduser(config["work_dir"]), name)
    if not config["debug"]:
        logger.info("deleting file: {}".format(name))
        try:
            if os.path.isdir(name):
                shutil.rmtree(name)  # , ignore_errors=True)
            else:
                os.unlink(name)
        except Exception as e:
            logger.error(str(e))
            return "rm_fail"
    return "ok"


rm_messages = {"invalid_id": "删除文件失败，可能是文件不存在，或已经不是重复文件",
               "rm_fail": "删除文件出错，可能是没有权限或文件正在使用中"}


@app.delete("/duplicated/<id:int>")
def delete_duplicated(db, id):
    status = remove_file_or_dir(db, id)
    return {"status": rm_messages.get(status, "未知错误，删除失败")}


@app.delete("/duplicated")
def delete_selected_dup(db, selected_dup):
    result_ok = []
    result_err = []
    for id in selected_dup.split(","):
        id = id.strip()
        status = remove_file_or_dir(db, id)
        if status=="ok":
            result_ok.append(id)
        else:
            result_err.append(id)
            if status=="invalid_id":
                continue
    return {"success": result_ok, "fail": result_err}


@app.get("/settings")
def get_settings():
    fields = ("work_dir", "quick_hash_size", "scan_interval")
    return {k: config[k] for k in fields}


@app.put("/settings")
def put_settings(**kwargs):
    if not kwargs.get("confirm"):
        work_dir = web.get_sysinfo("work_dir")
        if work_dir != kwargs.get("work_dir"):
            return {"confirm": "require"}
    web.set_sysinfo("work_dir", kwargs.get("work_dir"))
    fields = ("work_dir", "quick_hash_size", "scan_interval")
    for k in fields:
        config[k] = kwargs.get(k, config[k])
    save_config(config_name, config)
    return {}

