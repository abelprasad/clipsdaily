import json, urllib.request

GQL = "https://gql.twitch.tv/gql"
CID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
channels = ["kaicenat","ishowspeed","xqc","buddha","sykkuno","jynxzi","stableronaldo","zackrawrr","hasanabi","clix"]

def gql(query):
    req = urllib.request.Request(GQL, data=json.dumps({"query": query}).encode(),
        headers={"Client-ID": CID, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

for ch in channels:
    q = '''query { user(login: "%s") { id login stream { id type viewersCount } videos(first: 3, type: ARCHIVE, sort: TIME) { edges { node { id title createdAt lengthSeconds viewCount } } } } }''' % ch
    try:
        d = gql(q)
        u = (d.get("data") or {}).get("user")
        if not u:
            print(f"{ch}: NO USER"); continue
        live = u.get("stream") is not None
        vids = (u.get("videos") or {}).get("edges") or []
        print(f"{ch}: live={live} id={u.get('id')}")
        for e in vids:
            n = e["node"]
            print(f"   VOD {n['id']} | {n['createdAt']} | {int(n['lengthSeconds'])//60}m | views={n['viewCount']} | {n['title'][:80]}")
    except Exception as e:
        print(f"{ch}: ERROR {e}")
