import 'dart:convert';

import 'package:dio/dio.dart';

import '../models.dart';

/// Thin client for the Facegate server. One instance per project API key.
class FacegateClient {
  FacegateClient({required String baseUrl, required String apiKey, Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: baseUrl,
              headers: {'X-API-Key': apiKey},
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 30),
              validateStatus: (_) => true,
            ));

  final Dio _dio;

  Future<FaceSession> createSession({String? subjectId, String purpose = ''}) async {
    final r = await _dio.post<Map<String, dynamic>>('/v1/sessions',
        data: {'subject_id': subjectId, 'purpose': purpose});
    _throwIfError(r);
    return FaceSession.fromJson(r.data!);
  }

  Future<VerifyResult> verify({
    required String sessionId,
    required List<CapturedFrame> frames,
    required List<int> challengeDurationsMs,
    String? subjectId,
    Map<String, dynamic> client = const {},
  }) async {
    final meta = {
      'frames': [for (final f in frames) {'kind': f.kind, 'ts_ms': f.tsMs}],
      'challenge_durations_ms': challengeDurationsMs,
      'client': client,
    };
    final form = FormData.fromMap({
      'subject_id': ?subjectId,
      'meta': jsonEncode(meta),
      'frames': [
        for (final f in frames) MultipartFile.fromBytes(f.jpeg, filename: '${f.kind}.jpg'),
      ],
    });
    final r = await _dio.post<Map<String, dynamic>>('/v1/sessions/$sessionId/verify', data: form);
    if (r.statusCode == 200) return VerifyResult.fromJson(r.data!);
    return VerifyResult.clientError(_reasonCode(r), _detailMessage(r));
  }

  Future<Subject> enroll({
    required String externalId,
    required List<int> photoJpeg,
    String name = '',
    bool replace = false,
  }) async {
    final form = FormData.fromMap({
      'external_id': externalId,
      'name': name,
      'replace': replace.toString(),
      'photo': MultipartFile.fromBytes(photoJpeg, filename: 'photo.jpg'),
    });
    final r = await _dio.post<Map<String, dynamic>>('/v1/subjects', data: form);
    if (r.statusCode == 201) return Subject.fromJson(r.data!);
    final detail = r.data?['detail'];
    if (detail is Map<String, dynamic>) {
      throw FacegateException(_reasonCode(r), detail['details'] as Map<String, dynamic>?);
    }
    throw FacegateException(_reasonCode(r), {'detail': detail});
  }

  Future<List<Subject>> listSubjects() async {
    final r = await _dio.get<List<dynamic>>('/v1/subjects');
    _throwIfError(r);
    return r.data!.map((e) => Subject.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Subject> getSubject(String externalId) async {
    final r = await _dio.get<Map<String, dynamic>>('/v1/subjects/$externalId');
    _throwIfError(r);
    return Subject.fromJson(r.data!);
  }

  Future<void> deleteSubject(String externalId) async {
    final r = await _dio.delete<void>('/v1/subjects/$externalId');
    _throwIfError(r);
  }

  Future<List<VerificationRecord>> listVerifications({
    String? subjectId,
    String? purpose,
    bool? ok,
    int limit = 100,
  }) async {
    final r = await _dio.get<List<dynamic>>('/v1/verifications', queryParameters: {
      'subject_id': ?subjectId,
      'purpose': ?purpose,
      'ok': ?ok,
      'limit': limit,
    });
    _throwIfError(r);
    return r.data!.map((e) => VerificationRecord.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<ProjectPolicy> getPolicy() async {
    final r = await _dio.get<Map<String, dynamic>>('/v1/policy');
    _throwIfError(r);
    return ProjectPolicy.fromJson(r.data!);
  }

  /// Switches the preset and/or merges [overrides] into the project's policy.
  Future<ProjectPolicy> updatePolicy({String? preset, Map<String, dynamic>? overrides, bool merge = true}) async {
    final r = await _dio.put<Map<String, dynamic>>('/v1/policy',
        data: {'preset': ?preset, 'overrides': ?overrides, 'merge': merge});
    _throwIfError(r);
    return ProjectPolicy.fromJson(r.data!);
  }

  Future<ProjectPolicy> resetPolicy() async {
    final r = await _dio.delete<Map<String, dynamic>>('/v1/policy');
    _throwIfError(r);
    return ProjectPolicy.fromJson(r.data!);
  }

  Future<List<PolicyPreset>> listPresets() async {
    final r = await _dio.get<List<dynamic>>('/v1/policy/presets');
    _throwIfError(r);
    return r.data!.map((e) => PolicyPreset.fromJson(e as Map<String, dynamic>)).toList();
  }

  String _reasonCode(Response<dynamic> r) {
    final detail = r.data is Map ? (r.data as Map)['detail'] : null;
    if (detail is Map && detail['reason_code'] is String) return detail['reason_code'] as String;
    return 'HTTP_${r.statusCode}';
  }

  String? _detailMessage(Response<dynamic> r) {
    final detail = r.data is Map ? (r.data as Map)['detail'] : null;
    return detail is String ? detail : null;
  }

  void _throwIfError(Response<dynamic> r) {
    if (r.statusCode == null || r.statusCode! >= 400) {
      throw FacegateException(_reasonCode(r), r.data is Map ? (r.data as Map).cast<String, dynamic>() : null);
    }
  }
}
