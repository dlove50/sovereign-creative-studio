import io
from PIL import Image
from app.services import presentation
from test_cinematic_plan_storage import stored_api


def test_brand_visuals_persist_normalize_and_reject_foreign_access(stored_api):
    client, owner, _ = stored_api
    project = client.post("/api/projects",json={"name":"Original Brand"}).json()
    url = f"/api/projects/{project['id']}/brand-visuals"
    assert client.get(url).json() == {"colors":[],"fonts":[],"logos":[],"assets":[]}
    payload = {"colors":[{"name":"Background","hex":"#abcdef"}],"fonts":[{"role":"Body","family":"Arial"}]}
    assert client.put(url,json=payload).json()["colors"][0]["hex"] == "#ABCDEF"
    assert client.get(url).json()["fonts"] == payload["fonts"]
    assert client.get(f"/api/projects/{project['id']}/brand-kit").json()["primary_colors"] == "#ABCDEF"
    assert client.put(url,json={"colors":[{"name":"Bad","hex":"javascript:bad"}]}).status_code == 422
    owner[0] = "bob"
    assert client.get(url).status_code == 404
    assert client.put(url,json=payload).status_code == 404


def test_brand_upload_is_private_and_applies_to_slide(stored_api, tmp_path, monkeypatch):
    from app.routers import projects
    client, owner, _ = stored_api
    monkeypatch.setattr(projects.config,"STORAGE_DIR",tmp_path)
    project = client.post("/api/projects",json={"name":"Logo Brand"}).json()
    url = f"/api/projects/{project['id']}/brand-assets"
    buffer = io.BytesIO()
    Image.new("RGB",(80,40),"red").save(buffer,format="PNG")
    saved = client.post(url,files={"file":("logo.png",buffer.getvalue(),"image/png")})
    assert saved.status_code == 201, saved.text
    logo = saved.json()["logos"][0]
    assert client.get(logo["url"]).content.startswith(b"\x89PNG")
    assert client.get(f"/storage/brand/{project['id']}/{logo['url'].split('/')[-1]}").status_code == 404
    assert client.post(url,files={"file":("logo.svg",b"<svg><script/></svg>","image/svg+xml")}).status_code == 422
    deck = presentation.Deck(title="Brand test",slides=[presentation.Slide(title="A",bullets=["One"],narration="One")]*2)
    visuals = {"colors":[{"name":"Background","hex":"#ABCDEF"}],"fonts":[]}
    path = tmp_path / "brand" / project["id"] / logo["url"].split("/")[-1]
    images = presentation.render(deck,tmp_path / "rendered",visuals,path)
    with Image.open(images[0]) as image:
        assert image.getpixel((0,0)) == (171,205,239)
        assert image.getpixel((1480,840)) == (255,0,0)
    owner[0] = "bob"
    assert client.get(logo["url"]).status_code == 404
    assert client.post(url,files={"file":("logo.png",buffer.getvalue(),"image/png")}).status_code == 404


def test_site_import_merges_without_duplicates_and_authorizes_first(stored_api, monkeypatch):
    from app.routers import projects
    client, owner, _ = stored_api
    project = client.post('/api/projects',json={'name':'Site Brand'}).json()
    base=f"/api/projects/{project['id']}"
    calls=[]
    def detect(url):
        calls.append(url)
        return {'url':url,'name':'Detected','colors':['#abc','#AABBCC','#123456'],'fonts':['Inter','Inter'],'logo_candidates':['https://example.com/logo.png']}
    monkeypatch.setattr(projects.brand_spec,'import_site',detect)
    for _ in range(2):
        response=client.post(base+'/brand-visuals/import-site',params={'source_url':'https://example.com'})
        assert response.status_code==200,response.text
    spec=client.get(base+'/brand-visuals').json()
    assert len(spec['colors'])==2 and len(spec['fonts'])==1
    assert spec['logos']==[]  # candidates are not stored as private assets
    owner[0]='bob'
    assert client.post(base+'/brand-visuals/import-site',params={'source_url':'https://example.com'}).status_code==404
    monkeypatch.setattr(projects.brand_spec,'fetch_image',lambda url: (_ for _ in ()).throw(AssertionError('must authorize first')))
    assert client.post(base+'/brand-assets/fetch-url',params={'image_url':'https://example.com/logo.png'}).status_code==404
    assert len(calls)==2


def test_remote_asset_roundtrip_and_delete_by_filename(stored_api,tmp_path,monkeypatch):
    from app.routers import projects
    client,owner,_=stored_api
    monkeypatch.setattr(projects.config,'STORAGE_DIR',tmp_path)
    project=client.post('/api/projects',json={'name':'Remote Brand'}).json()
    base=f"/api/projects/{project['id']}"
    image=io.BytesIO();Image.new('RGB',(20,20),'blue').save(image,format='PNG')
    monkeypatch.setattr(projects.brand_spec,'fetch_image',lambda url:(image.getvalue(),'.png'))
    saved=client.post(base+'/brand-assets/fetch-url',params={'image_url':'https://example.com/logo.png','kind':'logos'})
    assert saved.status_code==201,saved.text
    asset=saved.json()['logos'][0]
    assert client.get(asset['url']).status_code==200
    assert client.delete(asset['url'],params={'kind':'logos'}).status_code==200
    assert client.get(asset['url']).status_code==404
    assert not (tmp_path/'brand'/project['id']/asset['url'].split('/')[-1]).exists()
