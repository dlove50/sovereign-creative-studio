import copy
import pytest
from app.services import performance_reference as reference


def tracks():
    return {'width':640,'height':368,'fps':25,'frames':[{'frame':i,'time':i/25,'keypoints':[[100.,100.] for _ in range(134)],'scores':[.9]*134} for i in range(53)]}


def test_joint_interpolation_preserves_original_mouth_and_other_arm():
    original=tracks();saved=copy.deepcopy(original)
    result=reference.apply_edits(original,[{'joint':'left_wrist','keyframes':[{'time':0,'dx':0,'dy':0},{'time':1,'dx':.1,'dy':-.1},{'time':2.08,'dx':0,'dy':0}]}])
    assert original==saved
    for index in reference.GROUPS['left_wrist']:
        assert result['frames'][25]['keypoints'][index]==pytest.approx([164,63.2])
    for index in set(range(134))-set(reference.GROUPS['left_wrist']):
        assert result['frames'][25]['keypoints'][index]==original['frames'][25]['keypoints'][index]
    assert result['frames'][0]==original['frames'][0]
    assert result['frames'][-1]==original['frames'][-1]


@pytest.mark.parametrize('keys',[[{'time':float('nan'),'dx':0,'dy':0}],[{'time':3,'dx':0,'dy':0}],[{'time':0,'dx':.26,'dy':0}],[{'time':1,'dx':0,'dy':0},{'time':0,'dx':0,'dy':0}]])
def test_invalid_keyframes_refused(keys):
    with pytest.raises(ValueError):reference.validate_edits([{'joint':'left_wrist','keyframes':keys}],2.08)


def test_transfer_cache_changes_for_edits_and_reference_content(tmp_path):
    source=tmp_path/'ref.mp4';source.write_bytes(b'video');track=tmp_path/'tracks.json';track.write_bytes(b'tracks')
    ref={'source':str(source),'tracks':str(track),'edits':[]};a=reference.transfer_key('own-vocal-cache',ref)
    ref['edits']=[{'joint':'head','keyframes':[{'time':0,'dx':.1,'dy':0}]}]
    assert reference.transfer_key('own-vocal-cache',ref)!=a
    ref['edits']=[];source.write_bytes(b'another video');assert reference.transfer_key('own-vocal-cache',ref)!=a


def test_continuation_trims_only_five_overlap_frames_and_keeps_separate_guides():
    w=reference.workflow(identity='original.png',pose='pose.mp4',face='own-face.mp4',background='bg.mp4',mask='mask.mp4',audio='own.wav',seed=7,length=57,previous='previous.mp4')
    assert w['14']['inputs']['video_frame_offset']==5 # precut guides start five frames before the new segment
    assert w['14']['inputs']['pose_video']!=w['14']['inputs']['face_video']
    assert w['28']['inputs']['length']==52
    assert w['28']['inputs']['batch_index']==['14',4]
    assert w['7']['inputs']['image']=='original.png'
    assert w['18']['inputs']['audio']=='own.wav'
