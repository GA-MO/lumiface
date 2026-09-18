import 'package:dio/dio.dart';
import 'package:lumiface/lumiface.dart';

/// The app's side of `examples/backend`: plain HTTP to *your* backend, which holds the
/// project key and talks to Lumiface. Nothing in here is a secret; it is what any app
/// does with any backend. Replace the routes with your own.
class ExampleBackend {
  ExampleBackend(String baseUrl)
      : _dio = Dio(BaseOptions(baseUrl: baseUrl, connectTimeout: const Duration(seconds: 10), validateStatus: (_) => true));

  final Dio _dio;

  /// `POST /api/face/session` — the backend fixes the subject and returns Lumiface's JSON.
  Future<FaceSession> createSession({String? subjectId, String purpose = ''}) async =>
      FaceSession.fromJson(_ok(await _dio.post('/api/face/session', data: {'subject_id': subjectId, 'purpose': purpose})));

  /// `POST /api/face/enrol-token` — a single-use token to enrol this one subject.
  Future<String> createEnrolToken(String externalId, {String name = ''}) async =>
      _ok(await _dio.post('/api/face/enrol-token', data: {'subject_id': externalId, 'name': name}))['token'] as String;

  /// `POST /api/face/done` — the backend reads the verdict from Lumiface for itself.
  Future<VerifyResult?> done(String sessionId) async {
    final j = _ok(await _dio.post('/api/face/done', data: {'session_id': sessionId}));
    return j['result'] is Map ? VerifyResult.fromJson((j['result'] as Map).cast<String, dynamic>()) : null;
  }

  Future<List<Subject>> listSubjects() async =>
      [for (final e in _okList(await _dio.get('/api/face/subjects'))) Subject.fromJson(e)];

  Future<Subject> enrolPhoto({required String externalId, required String name, required List<int> photoJpeg}) async =>
      Subject.fromJson(_ok(await _dio.post('/api/face/subjects',
          data: FormData.fromMap({
            'external_id': externalId,
            'name': name,
            'replace': 'true',
            'photo': MultipartFile.fromBytes(photoJpeg, filename: 'photo.jpg'),
          }))));

  Future<void> deleteSubject(String externalId) async => _ok(await _dio.delete('/api/face/subjects/$externalId'));

  Future<List<VerificationRecord>> listVerifications({String? purpose}) async => [
        for (final e in _okList(await _dio.get('/api/face/verifications', queryParameters: {'purpose': ?purpose})))
          VerificationRecord.fromJson(e)
      ];

  Future<ProjectPolicy> getPolicy() async => ProjectPolicy.fromJson(_ok(await _dio.get('/api/face/policy')));

  Future<ProjectPolicy> setPreset(String preset) async =>
      ProjectPolicy.fromJson(_ok(await _dio.put('/api/face/policy', data: {'preset': preset})));

  Future<List<PolicyPreset>> listPresets() async =>
      [for (final e in _okList(await _dio.get('/api/face/policy/presets'))) PolicyPreset.fromJson(e)];

  Map<String, dynamic> _ok(Response<dynamic> r) {
    if (r.statusCode == null || r.statusCode! >= 400) throw _error(r);
    return r.data is Map ? (r.data as Map).cast<String, dynamic>() : const {};
  }

  List<Map<String, dynamic>> _okList(Response<dynamic> r) {
    if (r.statusCode == null || r.statusCode! >= 400) throw _error(r);
    return [for (final e in r.data as List) (e as Map).cast<String, dynamic>()];
  }

  LumifaceException _error(Response<dynamic> r) {
    final detail = r.data is Map ? (r.data as Map)['detail'] : null;
    if (detail is Map && detail['reason_code'] is String) {
      return LumifaceException(detail['reason_code'] as String, detail.cast<String, dynamic>());
    }
    return LumifaceException('HTTP_${r.statusCode}', {'detail': detail});
  }
}
